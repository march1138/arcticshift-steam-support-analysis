# Arctic Shift Steam Support Analysis

A small, private-analysis workflow for examining public r/SteamSupport discussions archived by Arctic Shift.

## Purpose

This project supports interview preparation by exploring an outside-in sample of public Steam support discussions. The initial window is **March 1 through July 31, 2026**.

Questions include:

- What kind of support did the user need?
- Does the discussion indicate that the issue was resolved?
- If resolved, what appears to have resolved it?
- Who supplied useful information: community, original poster, Valve/Steam Support, another party, or unclear?
- Which parts appear amenable to self-service or AI-assisted support, and where does human judgment appear important?

This is exploratory analysis of public discussions. It is **not** intended to estimate Valve's internal support-ticket mix or performance.

## Data source

The collector queries the independent **Arctic Shift** historical archive. It does **not** access Reddit's API, scrape reddit.com, or automate Reddit's web interface.

Arctic Shift API documentation:
https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md

## Workflow

1. Arctic Shift API
2. Python collector
3. Local raw JSONL snapshot
4. LLM classification
5. Structured analysis dataset
6. Aggregate statistics and interview observations

The collector is deliberately non-semantic. It retrieves and structures archived posts and comments; it does not decide whether a thread is a support request, classify the issue, or determine whether it was resolved.

## Privacy and repository hygiene

- Raw data and analysis outputs remain local and are excluded from Git.
- Reddit usernames are not written to output. Authors are represented by thread-local pseudonyms such as `OP`, `USER_001`, and `USER_002`.
- No private Reddit data is accessed.
- The source dataset will not be republished from this repository.
- The analysis is not used to train or fine-tune an AI model.

## Installation

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run from GitHub Actions

Open the repository's **Actions** tab, choose **Run Arctic Shift Collection**, then choose **Run workflow**.

For the first validation run, use the defaults:

- subreddit: `SteamSupport`
- after: `2026-03-01`
- before: `2026-08-01`
- max_posts: `5`

When the run finishes, open the workflow run and download the artifact at the bottom of the run summary. It contains `steamsupport.jsonl`.

After validating the five-thread sample, set `max_posts` to `0` for an unlimited run across the selected date range.

GitHub Actions artifacts are retained for 7 days.

## Collect locally

```bash
python collect_arcticshift.py --subreddit SteamSupport --after 2026-03-01 --before 2026-08-01 --output data/steamsupport_2026-03-01_2026-07-31.jsonl\n\n# Five-post validation run\npython collect_arcticshift.py --subreddit SteamSupport --after 2026-03-01 --before 2026-08-01 --max-posts 5 --output data/test.jsonl
```

The collector uses ascending date pagination and requests at most 100 posts at a time. For each post it requests the archived comment tree, then writes one JSON object per thread.

## Notes

Arctic Shift is an independent archive and provides no uptime or performance guarantees. Its documentation asks normal users to keep request rates modest and use monthly dumps for massive workloads. This collector pauses between requests and honors HTTP 429 retry timing when available.
