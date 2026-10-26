# Open-source integration plan

This is an evaluation register, **not** a record of installed software. Review each project's current license and dependency notices before incorporating code.

| Project | Intended reuse | Initial decision |
| --- | --- | --- |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Coding agent and isolated task workspaces | Evaluate first |
| [OpenHands Agent SDK](https://github.com/OpenHands/software-agent-sdk) | Agent interfaces | Evaluate after OpenHands |
| [OpenHands Automation](https://github.com/OpenHands/automation) | Background task patterns | Study, do not install yet |
| [OpenCode](https://github.com/anomalyco/opencode) | Alternative coding worker | Compare against OpenHands |
| [CrewAI](https://github.com/crewAIInc/crewAI) | Specialist roles | Reference |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Checkpoints and approval gates | Optional later |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Multi-agent handoff patterns | Reference |
| [AutoGen](https://github.com/microsoft/autogen) | Earlier agent designs | Reference only |
| [Open WebUI](https://github.com/open-webui/open-webui) | Optional local chat UI | Evaluate separately |
| [Ollama](https://github.com/ollama/ollama) | Local model server | Check hardware first |
| [Gitea](https://github.com/go-gitea/gitea) | Optional self-hosted Git | Defer; GitHub already connected |

## V0.1 acceptance test

A coding worker receives one narrowly scoped task, edits only a disposable checkout, runs existing tests, records commands and changes, and prepares a PR requiring human review. No access to live H.E.R.B.I.E. controls or deployment credentials.
