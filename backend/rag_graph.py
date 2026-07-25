"""
Agentic RAG graph — extracted from the notebook so it can run as a standalone
service (FastAPI) instead of only inside Jupyter/Colab.

Same logic as the notebook: retrieve -> grade_documents -> (web_search) ->
generate -> grade_generation -> self-correct, with a retry cap.
"""
import base64
import os
from pathlib import Path
from typing import List, TypedDict

import fitz  # PyMuPDF
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# --- Config -----------------------------------------------------------------

CHAT_MODEL = "gemini-2.0-flash"
EMBEDDING_MODEL = "models/embedding-001"
VISION_MODEL = "gemini-2.0-flash"
EMBEDDING_DIM = 768

QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_db")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "agentic_rag_gemini")
TOP_K = int(os.getenv("TOP_K", "4"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=temperature)


def get_vision_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=VISION_MODEL, temperature=0.0)


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)


_qdrant_client = QdrantClient(path=QDRANT_PATH)
_existing = [c.name for c in _qdrant_client.get_collections().collections]
if QDRANT_COLLECTION not in _existing:
    _qdrant_client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )

vectorstore = QdrantVectorStore(
    client=_qdrant_client,
    collection_name=QDRANT_COLLECTION,
    embedding=get_embeddings(),
)

# --- Ingestion ---------------------------------------------------------------


def caption_image(image_bytes: bytes, vision_llm) -> str:
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    msg = HumanMessage(content=[
        {"type": "text", "text": (
            "Describe this image/diagram in 1-3 sentences, focusing on any "
            "text, labels, numbers, or technical content visible in it. "
            "Be factual and specific."
        )},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ])
    return vision_llm.invoke([msg]).content


def load_pdf(path: Path, vision_llm) -> list:
    docs = []
    pdf = fitz.open(path)
    for page_num, page in enumerate(pdf, start=1):
        text = page.get_text().strip()
        if text:
            docs.append(Document(page_content=text,
                                  metadata={"source": path.name, "page": page_num, "type": "text"}))
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = pdf.extract_image(xref)
            image_bytes = base_image["image"]
            if len(image_bytes) < 3000:
                continue
            try:
                caption = caption_image(image_bytes, vision_llm)
            except Exception:
                continue
            docs.append(Document(
                page_content=f"[Image] {caption}",
                metadata={"source": path.name, "page": page_num, "type": "image", "image_index": img_index},
            ))
    pdf.close()
    return docs


def load_text_file(path: Path) -> list:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [Document(page_content=text, metadata={"source": path.name, "type": "text"})]


def run_ingest(source_path: str) -> int:
    """Ingest a single file (PDF/txt/md) into the vector store. Returns chunk count."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Not found: {source_path}")

    vision_llm = get_vision_llm()
    if path.suffix.lower() == ".pdf":
        raw_docs = load_pdf(path, vision_llm)
    elif path.suffix.lower() in {".txt", ".md"}:
        raw_docs = load_text_file(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    if not raw_docs:
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(raw_docs)
    vectorstore.add_documents(chunks)
    return len(chunks)


# --- Graph state --------------------------------------------------------------


class GraphState(TypedDict, total=False):
    question: str
    generation: str
    documents: List[str]
    sources: List[dict]
    web_used: bool
    retries: int
    steps: List[str]


class RelevanceGrade(BaseModel):
    binary_score: str = Field(description="'yes' or 'no'")


class GroundednessGrade(BaseModel):
    binary_score: str = Field(description="'yes' - grounded, 'no' - made up")


class AnswersQuestionGrade(BaseModel):
    binary_score: str = Field(description="'yes' or 'no'")


# --- Nodes ----------------------------------------------------------------


def retrieve(state: GraphState) -> dict:
    question = state["question"]
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    docs = retriever.invoke(question)
    return {
        "documents": [d.page_content for d in docs],
        "sources": [
            {"source": d.metadata.get("source", "unknown"), "page": d.metadata.get("page"),
             "type": d.metadata.get("type", "text")}
            for d in docs
        ],
        "web_used": False,
        "retries": 0,
        "steps": ["retrieve"],
    }


_relevance_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a grader assessing relevance of a retrieved document chunk to a "
               "user question. Give a binary score 'yes' or 'no'. 'yes' means the chunk "
               "contains keywords or semantic meaning related to the question, even partially."),
    ("human", "Retrieved chunk:\n\n{document}\n\nUser question: {question}"),
])


def grade_documents(state: GraphState) -> dict:
    llm = get_llm()
    grader = _relevance_prompt | llm.with_structured_output(RelevanceGrade)
    question = state["question"]
    docs = state["documents"]
    sources = state.get("sources", [])

    kept_docs, kept_sources = [], []
    for doc, src in zip(docs, sources):
        result = grader.invoke({"document": doc, "question": question})
        if result.binary_score.strip().lower().startswith("y"):
            kept_docs.append(doc)
            kept_sources.append(src)

    return {
        "documents": kept_docs,
        "sources": kept_sources,
        "steps": state.get("steps", []) + ["grade_documents"],
    }


def route_after_grade(state: GraphState) -> str:
    if len(state.get("documents", [])) == 0:
        return "web_search"
    return "generate"


def web_search(state: GraphState) -> dict:
    question = state["question"]
    tool = TavilySearchResults(max_results=4)
    items = tool.invoke({"query": question})
    new_docs = [item.get("content", "") for item in items]
    new_sources = [{"source": item.get("url", "web"), "page": None, "type": "web"} for item in items]
    return {
        "documents": state.get("documents", []) + new_docs,
        "sources": state.get("sources", []) + new_sources,
        "web_used": True,
        "steps": state.get("steps", []) + ["web_search"],
    }


_generate_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an assistant answering questions using ONLY the provided context. "
               "If the context does not contain the answer, say you don't know — do not "
               "make anything up. Answer in the same language as the question. Be concise "
               "and cite which piece of context you used when relevant."),
    ("human", "Context:\n\n{context}\n\nQuestion: {question}"),
])


def generate(state: GraphState) -> dict:
    llm = get_llm(temperature=0.2)
    chain = _generate_prompt | llm
    context = "\n\n---\n\n".join(state.get("documents", []))
    question = state["question"]
    response = chain.invoke({"context": context, "question": question})
    return {
        "generation": response.content,
        "retries": state.get("retries", 0) + 1,
        "steps": state.get("steps", []) + ["generate"],
    }


_groundedness_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a grader assessing whether an answer is grounded in / supported by "
               "a given set of facts. Give a binary score 'yes' or 'no'. 'yes' means the "
               "answer is supported by the facts, with no fabricated claims."),
    ("human", "Facts:\n\n{documents}\n\nAnswer: {generation}"),
])

_answers_question_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a grader assessing whether an answer actually resolves a user "
               "question. Give a binary score 'yes' or 'no'."),
    ("human", "Question: {question}\n\nAnswer: {generation}"),
])


def route_after_generate(state: GraphState) -> str:
    if state.get("retries", 0) >= MAX_RETRIES:
        return "useful"

    llm = get_llm()
    documents = "\n\n".join(state.get("documents", []))
    generation = state["generation"]
    question = state["question"]

    grounded = (
        (_groundedness_prompt | llm.with_structured_output(GroundednessGrade))
        .invoke({"documents": documents, "generation": generation})
        .binary_score.strip().lower().startswith("y")
    )
    if not grounded:
        return "not_grounded"

    answers = (
        (_answers_question_prompt | llm.with_structured_output(AnswersQuestionGrade))
        .invoke({"question": question, "generation": generation})
        .binary_score.strip().lower().startswith("y")
    )
    if not answers:
        return "not_useful"

    return "useful"


# --- Assemble the graph -----------------------------------------------------

_g = StateGraph(GraphState)
_g.add_node("retrieve", retrieve)
_g.add_node("grade_documents", grade_documents)
_g.add_node("web_search", web_search)
_g.add_node("generate", generate)

_g.set_entry_point("retrieve")
_g.add_edge("retrieve", "grade_documents")
_g.add_conditional_edges("grade_documents", route_after_grade,
                          {"web_search": "web_search", "generate": "generate"})
_g.add_edge("web_search", "generate")
_g.add_conditional_edges("generate", route_after_generate,
                          {"useful": END, "not_grounded": "generate", "not_useful": "web_search"})

rag_app = _g.compile()
