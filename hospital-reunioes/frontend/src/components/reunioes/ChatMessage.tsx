"use client";

import { Bot, User } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@/types/chat";

interface ChatMessageProps {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
          isUser
            ? "bg-gradient-to-br from-primary to-primary-dark"
            : "bg-slate-100"
        }`}
      >
        {isUser ? (
          <User className="w-3.5 h-3.5 text-white" />
        ) : (
          <Bot className="w-3.5 h-3.5 text-slate-600" />
        )}
      </div>
      <div
        className={`max-w-[80%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
          isUser
            ? "bg-gradient-to-r from-primary to-primary-dark text-white rounded-tr-sm"
            : "bg-slate-50 text-slate-700 border border-slate-100 rounded-tl-sm"
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
