Q: Why is prior conversation context resent with every turn? How is a system prompt different from a user message? Why do input tokens grow over a conversation? What eventually limits that growth?

A:
LLMs are stateless APIs. They do not maintain an internal persistent memory between distinct HTTP requests. The model would have zero awareness if there was no memory context in each turn of conversation. 
The system prompt defines global guidelines, rules, persona, and output constraints. User messages represent dynamic inputs, questions, or commands evaluated within those system-defined rules.
Input Tokens grow because each turn appends both user’s new message and the past conversational history stack. 
Even though input tokens grow, there are things that can limit that growth: Model Context Window, which are hard token limits set by the architecture, Hardware VRAM limits, which are memory constraints on underlying GPUs, and Cost & Latency.
