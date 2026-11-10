# AI Tool Usage

## Tools I Used
- **Claude Code** for the whole project: requirements, architecture, spec, test-first implementation, test runs and docs. I switched models from task to task: **Sonnet** for clear, routine work, and **Opus** for the core parts and for concurrency and security. The model planned for each task is in `docs/chatbot-tasks.md`.
- **My own workflow skill for Claude Code**, which I built on the spec-driven development (SPDD) framework before starting. It splits the work into 6 stages: requirements, architecture, spec and test plan, test-first implementation, test execution, submission. Each stage ends with my approval.
- **Independent reviewer agents** (separate Claude Code agents) that checked the architecture and the spec before I approved them.
- **Google Gemini** is the LLM inside the chatbot, not a development tool.

Every AI mistake and fix was logged as it happened in `docs/ai-usage-log.md` (31 entries). This file is a summary of that log.

## What Helped Most
1. **Building the workflow skill first.** At the start, I built a skill based on the spec-driven development (SPDD) framework, and it proved helpful for the project.
2. **Finding holes before the code existed.** A reviewer agent tried the calculator spec's values in Python and found that `1e999` and `1e308*10` give infinity, which would crash the JSON response with a 500, and that `((2**1000)**1000)**1000` passes the exponent limit while building a huge integer. While writing the database tests, Claude also ran a small SQLite probe and found that the spec contradicted itself: the read-only authorizer rejects `WITH RECURSIVE`, so the planned slow-query test would have passed for the wrong reason. Both were fixed in the spec before any code was written.
3. **Mutation checks.** After each task, Claude broke the new code on purpose (for example: not removing old thinking blocks, no 20-turn trim, a failed turn still replayed) and checked that a test failed each time. This found real gaps. Removing the database's read-only mode broke no test, because the authorizer alone already blocked writes; the read-only layer now has its own test.

## What I Had to Fix
1. **Separation of concerns.** Learning separation of concerns was one of my goals, but the AI-written workflow and architecture never said so, and the first code had leaks: the LLM client took the app's whole `Settings`, and the chat service read provider-specific response fields and listed tool names by hand. I asked about it. We added a requirement (NFR-12), a layer table, and an import test (`tests/test_architecture.py`) that fails on a forbidden import. When the LLM provider later changed from Claude to Gemini, the services and the HTTP layer didn't change at all.
2. **Problems found only in my manual tests.** The AI-written weather tool never said its unit, so real Gemini reported the °C mock temperatures as °F. The tool description now says "Temperature is in °C." In my manual test scripts, Claude also used `$b` and `$B` as two variables, but PowerShell names ignore case, so one overwrote the other.

## What AI Struggled With
- **Trusting its own edits.** Some of Claude's `sed` and inline-Python edits silently didn't apply, and one `git checkout` restored the wrong version of a file during a mutation check. The test results then made no sense. Claude noticed both and redid them, but it showed that a green test run means little if you don't know which code ran.
- **Real LLM behavior.** Gemini answered "What is 1/0?" from its own knowledge instead of using the calculator (0 of 3 first runs used it), although the description said "never calculate in your head". Only measuring repeated real runs showed how often this happened; stronger wording in the tool description and instructions got it to 25 of 25. A Gemini SDK example from the docs also didn't work with the installed version (`id=` rejected), so the code builds that part by hand.
- **Testing rules it had set itself.** The first real-LLM tests only skipped when there was no key, so a plain `pytest` with a key in `.env` called real Gemini, against our rule that normal tests never do. They are now off unless you run `pytest -m real_llm`.
- **Keeping track of the whole process.** Keeping track of the entire process is not simple. It requires a high level of focus, or experience with structured, systematic workflows, to minimize errors.
