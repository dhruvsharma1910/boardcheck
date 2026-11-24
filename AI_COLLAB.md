# How I worked with the AI

<!-- DRAFT. Everything here happened and can be found in chat/full-chat.md.
     Lines marked TODO are mine to write: the AI does not know my reasons and
     must not make them up. Delete this note when they are filled in. -->

I used Claude Code for this project. It wrote the code, the tests and the first
draft of these documents. I chose the task, made the decisions in part 1, and
reviewed the decisions in part 2. The full history, from my first prompt, is in
[chat/full-chat.md](chat/full-chat.md).

## Part 1. Decisions I made

## Decision 1: what may be downloaded
AI suggested: four downloads: Python packages, the Archify diagram tool, DINOv2 weights (85 MB), and real board photos (VisA, 1.8 GB)
I decided: Python packages only. Later, when the AI asked again because the brief requires the diagram, I approved Archify too. DINOv2 and the photos stayed out
Why: TODO
Evidence: chat excerpt #1. It shaped everything after: the practice boards are drawn by our own code, and DINOv2 is listed as "not tested" instead of being given a made-up score

## Decision 2: how to choose the detection method
AI suggested: three ways: benchmark first, classical only, or neural from the start. It recommended the benchmark
I decided: benchmark, then choose
Why: TODO
Evidence: chat excerpt #2, [bench/RESULTS.md](bench/RESULTS.md)

## Decision 3: what a close call looks like
AI suggested: a third "check by eye" state, or always decide, or lean towards missing. It recommended the third state and said it goes slightly beyond the brief
I decided: the third state
Why: TODO
Evidence: chat excerpt #2. On the unseen test boards: 51 of 7,616 part checks were sent to the operator: 21 parts really missing and 30 really present. Without the third state each would have been a guess

## Decision 4: how the user points out a part
AI suggested: click or drag, drag only, or detect everything automatically. It recommended click or drag
I decided: click or drag
Why: TODO
Evidence: chat excerpt #2. One click gives a good box for 103 of 120 parts (`python -m unittest`); the rest are dragged

## Part 2. Decisions the AI made, for me to accept or overrule

These were made by the AI while building. Each has evidence. The brief asks how I
steered, so each needs my verdict, and some should change if I disagree.

## Decision 5: delete the light-matching stage
AI suggested: first to build it, then to delete its own work
Evidence: photos fully right on development boards: 97.2% with it, 98.1% without. Kept in `bench/dropped_light.py`
I decided: TODO (accept or overrule)
Why: TODO

## Decision 6: judge each difference against the photo's own noise
AI suggested: raw differences at first; after reading the misses, ratios to a noise floor
Evidence: commit "Judge differences against each photo's own noise floor". Development photos fully right went from 94.1% to 96.9%
I decided: TODO
Why: TODO

## Decision 7: keep a set of boards nobody has looked at
AI suggested: demote its own test set after it had looked at the results, and make a new one to be run once
Evidence: chat, after the first benchmark; `SPLITS` in `bench/dataset.py`
I decided: TODO
Why: TODO

## Decision 8: refuse a photo that does not line up
AI suggested: a fourth result, "can't check", instead of judging the wrong board
Evidence: Alignment quality on the right board: min 0.80, median 0.98 (480 photos). On a different board: max 0.02, median 0.01 (60 photos). The cut-off is 0.30
I decided: TODO
Why: TODO

## Decision 9: test the demo's failure modes, not only the average
AI suggested: tests for a moved board on a patterned table, a plain board, turned and resized photos, the wrong board
Evidence: four of them failed the first time although the benchmark looked good. The worst: a part missing from a perfectly plain board was not reported as missing
I decided: TODO
Why: TODO

## Chat excerpt #1
> AI: Which downloads may I make? All are build-time only; the finished app runs offline.
> (options: Python packages / Archify / DINOv2-small weights / Real PCB photos)
> me: Python packages
> AI: You approved Python packages only, so I won't download Archify, the DINOv2 weights or the real photos.
> (later) AI: May I download Archify and make the required diagram?
> me: Yes, use Archify

## Chat excerpt #2
> AI: How should the detector be built? The demo gives one good photo of an unseen board, so there is nothing to train on.
> me: Benchmark, then choose
> AI: When a part is a close call, what should the operator see?
> me: Third state: check by eye
> AI: How should the user point out parts on the reference photo?
> me: Click or drag

## Chat excerpt #3
> AI: The same table says my light-matching stage now makes results worse (96.9% with it, 98.1% without), because the ring correction took over its job. So I'm deleting it.

## Where the AI was wrong

- Its first Archify description drew the benchmark inside the running app. Archify's own check refused it.
- It drew the red result banner with red text on red. Found by looking at the page, not by a test.
- Its first evidence formula scored an empty patch as a perfect match.
- A web search summary told it a paper used image subtraction and YOLO. The paper's abstract does not say so, and the claim was left out.
- It first ran the preview from a folder macOS protects, and the app hung until it was run from elsewhere.
