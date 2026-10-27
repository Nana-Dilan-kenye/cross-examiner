# The submission checklist

Everything the official rules ask for, with the path where it lives and
what still needs a human.

**Track:** Track 1 — Solving Fragmented Intelligence.
**Deadline:** 27 October 2026, 23:45 UTC (hard).

---

## 1. The four required components

| Component | Requirement (official-rules.md §10.1, submission-requirements.md §2) | Where it is | State |
|---|---|---|---|
| **Demo video** | 1–4 minutes, showing the main workflow, how the agent solves the challenge, its key features, and how Zetaris and Meterless are integrated | `docs/DEMO_SCRIPT.md` is the recording plan; the video itself has to be recorded | **needs a human** |
| **Slide deck** | the problem and target users, the solution, the agent workflow or architecture, the technical stack, how Zetaris and Meterless were used, what was unique about the use of the sponsor technologies, product visuals, future enhancements | `docs/SLIDES.md` | **needs a human** (to export it as slides and add the visuals) |
| **GitHub repository** | public, all source code, README covering setup, usage and dependencies | this repository, `README.md` | **needs a human** (make the repository public and push) |
| **Sponsor technology explanation** | how Zetaris and Meterless were integrated, how Cursor was used, where NVIDIA contributes, and what was unique about the use of the sponsor technologies | `README.md` § Disclosure and § The unified semantic layer | ready to copy into the form |

## 2. The submission form

From `submission-form-preview.md` §1. The fields, and where the answer comes from.

| Field | Answer | Ready? |
|---|---|---|
| Project name | Cross-Examiner | yes |
| Description (one sentence + a short paragraph) | `README.md` § first paragraph; `docs/SUBMISSION_CHECKLIST.md` §3 below | yes |
| Track | Track 1 — Solving Fragmented Intelligence | yes |
| Team members | the roster; **it locks when the first submission is created** | **needs a human** |
| GitHub repository URL | public URL | **needs a human** |
| Demo video | 1–4 minutes | **needs a human** |
| Slide deck | the eight points | **needs a human** |
| Sponsor technology explanation | Zetaris, Meterless, Cursor, NVIDIA, and what was unique | yes |
| **Pre-existing components** | **None.** Every commit in this repository is dated after the build window opened on 22 October 2026 00:00 UTC (the first is `571dff1`, 25 October 2026 15:44 UTC), and every piece of data was fetched or generated after it as well. The H-MEM reference engine and the Zetaris getting-started repository are open-source libraries, which do not need declaring. | yes |
| Colab links | not applicable: the project does not run in Colab | yes |

## 3. The description

> Cross-Examiner is an agent for public-health planners who must choose
> between conflicting immunization-coverage figures for the same country
> and year. It reads every published figure through a Zetaris Unified
> Semantic Layer that carries each number's lineage, tells a derived
> republication apart from an independent measurement, cross-examines
> the administrative figure against a household survey, remembers what it
> found, and returns a recommendation with its provenance — or an
> explicit "unresolved, a human has to look at this".

## 4. What is verified, and how

Every command below was run on this machine on 26–27 October 2026.

| Claim | Command | Result |
|---|---|---|
| the project works | `python3 -m unittest discover -s tests` | 256 tests, OK |
| the semantic layer is real and deployed | `python3 scripts/verify_usl.py` | 18/18 checks passed |
| the whole user journey works | `python3 scripts/verify_journey.py` | 8/8 steps passed |
| it works offline, with no credentials | `SAMPLE_MODE=true python3 scripts/verify_journey.py` | 8/8 checked, 2 not applicable offline |
| the checks find what was planted | `python3 eval/run_eval.py` | 6/6 planted detected, 0/12 false positives |
| the example answers are real | `python3 scripts/generate_examples.py` | 4 outputs from real runs |
| the container works | `docker build -t cross-examiner .` | built; `/health`, `/run`, the error paths and `/traces/<run_id>` all answered |
| the web UI works | `python3 -m unittest tests.test_ui` | 26 tests, OK; also exercised in a headless browser (41/41 checks) and verified inside the container |
| no key is committed | `python3 scripts/secret_scan.py` | no secrets in the repository or the traces |

## 5. The mandatory checklist from `disqualification-checklist.md`

| Check | State | Evidence |
|---|---|---|
| §1 the project was built during the build window | yes | every commit after 22 Oct 00:00 UTC |
| §2 the repository is public | **needs a human** | the repository has to be made public and pushed |
| §3 the README covers setup, usage, dependencies, agent roles, examples and limitations | yes | `README.md` |
| §5 there is a programmatic entry point that needs no interactive input | yes | `run.py` (`--once`, `--health`, service) |
| §7 `SAMPLE_MODE=true` works with an empty `.env` and no network | yes | `scripts/verify_journey.py` in sample mode |
| §9 the logs are generated during the run, written to stdout and `logs/`, name at least two agents, show agent-to-agent interaction, are more than a single pass, and contain a feedback, critique, retry or branch event | yes | `logs/trace-<run_id>.jsonl`; the fields and the five agents are in `README.md` § The trace |
| §10 Zetaris and Meterless are really integrated, behind adapters with timeouts and fallbacks | yes | `src/zetaris_source.py`, `src/model_client.py`; the adapters are documented |
| §11 no secrets are committed | yes | `scripts/secret_scan.py` |
| §12 the submission is complete | **needs a human** | the video, the deck and the form |
| §13 every claimed capability is one the code has; limitations are stated honestly | yes | the disclosure in `README.md`; the limitations section |

## 6. What only a human can do

1. Record the demo video (1–4 minutes) with `docs/DEMO_SCRIPT.md` in front of it.
2. Export the slide deck from `docs/SLIDES.md` and add the product visuals.
3. Make the repository public and push it.
4. Fill in the form on HackOS: project name, description, track, the
   roster, the repository URL, the video, the deck, the sponsor
   explanation, and the pre-existing-components declaration (none).
5. Watch for the announcements: the submission form, the judging
   updates and any request for clarification.

## 7. Things that must not happen

- Do not hand-edit a trace. A trace that does not match the code is an
  integrity problem, not a shortcut (`ai-usage-policy.md` §4.2).
- Do not show a key in the video or the deck. Check the terminal
  frames around the environment variables (`disqualification-checklist.md` §11).
- Do not claim anything the code does not do. The deck and the README
  must match the demo (`submission-form-preview.md` §3.6).
- Do not run `docker compose down -v` against the Zetaris instance: it
  deletes the metastore and the deployed semantic layer with it.
