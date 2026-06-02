export type Role = "user" | "TariqGPT";

export interface Message {
  role: Role;
  content: string;
  confidence_score?: number; // Optional confidence score, can be a string or number
}

