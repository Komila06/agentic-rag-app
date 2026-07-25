export type Source = {
  source: string;
  page: number | null;
  type: "text" | "image" | "web" | string;
};

export type ChatResponse = {
  answer: string;
  steps: string[];
  sources: Source[];
  web_used: boolean;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps?: string[];
  sources?: Source[];
  webUsed?: boolean;
  pending?: boolean;
};
