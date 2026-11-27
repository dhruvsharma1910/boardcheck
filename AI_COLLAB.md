# How I worked with the AI

I built this with Claude Code. The AI wrote the code, the tests, the benchmark and
the documents. That includes this file, which I asked it to write from the chat
record. I set the limits, chose between the options it gave me, and asked for the
testing and CI. The full chat, from my first prompt, is in
[chat/full-chat.md](chat/full-chat.md), and every decision and quote below can be
found there.

A note on the "Why" lines. In decisions 2 to 4, 6 and 7 I picked one of the options
the AI offered and did not type a reason, so the reason quoted is the text written on the
option I picked, plus my own words where I added some. Decisions 8 to 12 were made by the
AI while building, with its measured reasons. I left them in place.

## How we reached a shared understanding

1. **Before any code.** The AI read the brief and asked me four questions at once:
   what it could download, how to choose the detector, what a close call should
   look like, and how parts are pointed out. Each question came with options and
   one recommendation. My answers are [excerpt #1](#chat-excerpt-1).
2. **After the first build.** It reported what worked and what didn't, including a
   conflict between two of my answers: I asked for a benchmark against a neural
   model but did not allow the model to be downloaded. It also named its own weak
   spots. See [excerpt #2](#chat-excerpt-2).
3. **Required diagram.** It asked again for Archify, which the brief requires, and
   I approved it.
4. **Next day.** I moved the project to this GitHub account and asked for testing
   with CI/CD. See [excerpt #3](#chat-excerpt-3).
5. **Getting ready for the demo.** I asked for demo boards I would not have to name,
   then for a saved list of real boards (Arduino, ESP32, 8085, PYNQ, Basys). The AI
   explained why a list could not place parts on my own photos, and asked how to
   solve the naming instead. See [excerpt #4](#chat-excerpt-4). When I then asked for
   the meaning of each pin, it asked what that should do in the app, and I added that I
   must be able to teach it new boards. See [excerpt #5](#chat-excerpt-5).
6. **Every result** came back with what had not been checked. The biggest open
   risk is the same throughout: every number here comes from boards drawn by code,
   not real photographs.

## Part 1. Decisions I made

## Decision 1: what may be downloaded
AI suggested: four downloads: Python packages (~150 MB), the Archify diagram tool, DINOv2-small weights (~85 MB), and real board photos (the VisA set, a 1.8 GB file)
I decided: Python packages only. Later, when the AI asked again because the brief requires the diagram, I approved Archify too. DINOv2 and the photos were never downloaded
Why: the chat records the choice but no reason for it
Evidence: chat excerpts #1 and #2. It shaped everything after: the practice boards are drawn by our own code ([bench/synth.py](bench/synth.py)), and DINOv2 is listed in [RESEARCH.md](RESEARCH.md) as "not tested" instead of being given a score

## Decision 2: how to choose the detection method
AI suggested: three ways: benchmark first, classical only, or neural from the start. It recommended the benchmark
I decided: benchmark, then choose
Why: the option I picked said "Build a classical pipeline (align, normalise light, compare each part), test it against DINOv2 features on the same data, and keep whichever wins."
Evidence: [bench/RESULTS.md](bench/RESULTS.md), 480 photos of 60 boards never used for tuning. Photos fully right: this app 98.1%, template matching 82.9%, SSIM 69.4%, aligned pixel difference 49.8%, raw pixel difference 20.4%. Because of decision 1 the comparison has no DINOv2 column, and the AI said so (excerpt #2)

## Decision 3: what a close call looks like
AI suggested: a third "check by eye" state, or always decide, or lean towards missing. It recommended the third state
I decided: the third state
Why: the option I picked said "Verdict is OK, MISSING, or an amber 'check by eye' on that one part. Honest, but slightly more than the brief asks for."
Evidence: same 480 photos. Forced to answer present or missing, 9 photos contained a wrong answer. With the third state, 2 do: one missing part called present, one present part called missing. 51 of 7,616 part checks go to the operator, 21 really missing and 30 really present

## Decision 4: how the user points out a part
AI suggested: click or drag, drag only, or detect every part automatically. It recommended click or drag
I decided: click or drag
Why: the option I picked said "One click proposes a box around the part under the cursor; dragging draws your own. Boxes can be moved and resized." Auto-detect was described as "messy on unseen boards", and the demo board is unseen
Evidence: in the tests, one click gives a good box (overlap above 0.6) for 103 of 120 parts. The rest are dragged

## Decision 5: test it on clean machines, with CI
AI suggested: nothing until I asked. Its report the day before said "I haven't tested a clean install or Windows."
I decided: testing with CI/CD, on a new repo under this account. The AI proposed what CI should prove and I kept all of it: tests on Linux, macOS and Windows with Python 3.12 and 3.13, a first run on a clean machine of each, an install and check with the network cut, and a zip per system that installs with no internet
Why: in my words at the time, "THE GITHUB COMMITS WILL BE MONITORED", and the brief judges effort from GitHub history and requires the app to work fully offline
Evidence: excerpt #3, [.github/workflows/](.github/workflows/). All 10 CI jobs and all 3 bundle builds passed. Setting it up also found a real bug: on a Mac with only an older Python, `run.sh` failed with a confusing pip error. It now says what is needed

## Decision 6: a saved list of real boards, or let the app find the parts
AI suggested: I asked for a database of boards like Arduino, ESP32, 8085 kits, PYNQ and Basys, so I would not have to name parts. The AI said a list cannot place parts on my own photo, because the positions change with every photo and between versions and clones, and made-up positions would give wrong answers. It offered a "Find all parts" button, drawn look-alike boards, or both, and recommended the button
I decided: the button
Why: the option I picked said "A 'Find all parts' button. On a photo of any real board it boxes every part and names each one (Chip 1, Connector 2, Part 3…). You delete the wrong boxes instead of typing names. Not tested on real photos yet."
Evidence: on 40 development boards not used for tuning, 92% of parts got a box and 95% of the boxes were real parts. It is weakest on black boards (71%) and white boards (71%). Naming parts with nothing but its boxes, 160 photos gave no wrong answers; 19 asked the operator to look ([bench/find_eval.py](bench/find_eval.py)). My first real photo, a board held in my hand, showed boxes off the board; that was fixed the same day (see "Where the AI was wrong"). The boxes are named Part 1, Part 2 and so on, not Chip or Connector as the option said: the AI chose that because a guess from shape alone would sometimes be wrong. Just before this, for my demo, it added five practice boards with their parts already named ([samples/boards](samples/boards)); their 30 photos give no wrong answers. It is still untested on real photographs

## Decision 7: what knowing each pin's meaning should do
AI suggested: three options: label pins on the photo, a pin reference panel only, or name whole parts by fitting a saved layout to my photo. It recommended labelling, said the pin tables would come from the makers' own documents and not from memory, and that none of this helps with an unseen interview board
I decided: label pins on the photo, and let me teach it new boards
Why: the option I picked said "Box a header once and pick which one it is (e.g. 'Arduino digital 0-7', 'Basys 3 Pmod JA'). The app splits the box into pins and labels each one (D0, D1…; JA1 = FPGA pin J1). A missing or bent pin is then reported by its meaning." In my own words: "Let other be the optoin to choose those predetermined boards and allow us to teach it new boards for the interview"
Evidence: [boardcheck/pinouts.py](boardcheck/pinouts.py) and the built-in tables in [boardcheck/pinouts/](boardcheck/pinouts/), each naming the documents it was copied from: Arduino Uno R3, ESP32-DevKitC V4, Basys 3, PYNQ-Z2, Boolean Board and the Intel 8085 CPU chip. On 23 drawn boards with a header split into pins, complete photos gave no false alarms, every pin was flagged when the header was gone, and one painted-out pin was named in all 23 with no other pin flagged ([tests/test_engine.py](tests/test_engine.py), class `Pins`). Bent pins on real boards are untested

## Part 2. Decisions the AI made, which I left in place

## Decision 8: delete the light-matching stage
AI suggested: first to build it, then to delete its own work
I decided: deleted
Why: it made results worse once each part was corrected by the ring of board around it. Photos fully right: development boards 97.2% with it, 98.1% without; final boards 97.3% with it, 98.1% without
Evidence: [bench/RESULTS-dev.md](bench/RESULTS-dev.md), [bench/RESULTS.md](bench/RESULTS.md). The code stays in [bench/dropped_light.py](bench/dropped_light.py) so the row can be reproduced

## Decision 9: judge each difference against the photo's own noise
AI suggested: raw differences first; after reading the misses, ratios to a noise floor measured on untouched board in the same photo
I decided: kept
Why: a difference of 0.12 is damning in a sharp photo and ordinary in a blurred one. The change that brought this in, together with a core region that ignores leftover pads and a ring of board that cancels glare, took development photos fully right from 94.1% to 96.9%
Evidence: commit "Judge differences against each photo's own noise floor"; `noise_floor` and `features` in [boardcheck/evidence.py](boardcheck/evidence.py)

## Decision 10: keep a set of boards nobody has looked at
AI suggested: demote its own first test set, because it had looked at the results while designing, and draw 60 new boards to be run once after the method was frozen
I decided: kept
Why: a score on boards that shaped the design says nothing about the demo, where the board is unseen
Evidence: `SPLITS` in [bench/dataset.py](bench/dataset.py); commit "Freeze the method before the final test run", made before the final set was run

## Decision 11: refuse a photo that does not line up
AI suggested: a fourth result, grey "CAN'T CHECK", instead of judging what may be the wrong board
I decided: kept
Why: a photo of another board would otherwise get confident verdicts about parts it doesn't have
Evidence: alignment quality on the right board: lowest 0.80 in 480 photos. On a different board: highest 0.02 in 60 photos. The cut-off is 0.30, far from both

## Decision 12: keep the bare-board vote, and do not chase the black-board errors
AI suggested: keep the vote although it scored worse on the final boards (98.1% with it, 98.8% without), because changing it after seeing the final result would make that number meaningless. Later it drew 40 new black boards to study the weak spot, tried a fix, and recommended against it
I decided: kept the vote as it is
Why: on black boards the app already gives 1 wrong answer in 320 photos. The fix gave 0 wrong answers but 85 checks by eye instead of 82, and 98.4% instead of 98.1% on development boards. That is one answer either way, too small to justify changing a frozen method
Evidence: [RESEARCH.md](RESEARCH.md), section "Black parts on black boards"; [bench/dark_boards.py](bench/dark_boards.py), [bench/core_vote.patch](bench/core_vote.patch)

## Chat excerpt #1
The four questions at the start, with the options (labels as shown) and my answers.

> AI: Which downloads may I make? All are build-time only; the finished app runs offline. Python packages go in a venv inside PCB/, nothing is installed globally.
> (Python packages / Archify / DINOv2-small weights / Real PCB photos)
> AI: How should the detector be built? The demo gives one good photo of an unseen board, so there is nothing to train on.
> (Benchmark, then choose (Recommended) / Classical only / Neural from the start)
> AI: When a part is a close call, what should the operator see?
> (Third state: check by eye (Recommended) / Always decide / Lean towards missing)
> AI: How should the user point out parts on the reference photo?
> (Click or drag (Recommended) / Drag boxes only / Auto-detect everything)
> me: "Python packages", "Benchmark, then choose (Recommended)", "Third state: check by eye (Recommended)", "Click or drag (Recommended)"

## Chat excerpt #2
From its first full report, and the diagram that followed.

> AI: You chose "benchmark, then choose", but without the DINOv2 weights I could only compare classical methods. `RESEARCH.md` says so.
> AI: One of my own design pieces, the bare-board vote, scored slightly worse on the final test (98.1% with it, 98.8% without). I left it in, because changing it after seeing the final result would make the number meaningless.
> AI: May I download Archify and make the required diagram?
> me: Yes, use Archify
> AI: Archify's own check caught a real inaccuracy: the benchmark isn't part of the running app, so it belongs outside the frame.

## Chat excerpt #3
The next day.

> me: ... BUILD UP THIS PROJECT BY FRIDAY EVENING BY TESTING- WITH CI/CD AND OTHER THINGS TO SHOW THAT WE ARE MAKING GRADUAL PROGRESS AS THE GITHUB COMMITS WILL BE MONITORED
> me: I HAVE LOGGED INTO ANOTHER GITHUB ACCOUNT FOR THIS PROJECT SO CREATE A NEW REPO AND START
> AI: **CI:** runs the tests on Linux, Mac and Windows with two Python versions, a first run on a clean machine of each system, and an install and check with the network cut. Clean installs and Windows were both untested before.
> AI: **CD:** builds one zip per system that installs with no internet. All three were unpacked and gave the right answers on the sample photos. Pushing a version tag would only draft a release for you to publish.

## Chat excerpt #4
Getting ready for the demo, on 27 November.

> me: give me good and bad boards to show demo
> me: i can't sit and name all the parts myself for testing now
> me: Create a db of some basic boards- arduino, esp32, 8085, pynq, basys- boolean and analog, and all similar kind of boards, so i don't have to sit and rename anything
> AI: A saved list of real boards (Arduino, ESP32, 8085 kit, PYNQ, Basys, Boolean) can't name the parts in YOUR photo by itself. The app needs each part's exact position in your own reference photo, and layouts differ between versions and clones (Uno R3 vs R4 vs cheap clones; many ESP32 and 8085 kit versions). Making up positions would give wrong answers. Which should I build instead?
> (Auto-name parts (Recommended) / Drawn look-alike boards / Both)
> me: "Auto-name parts (Recommended)"

## Chat excerpt #5
Later the same day, asking for pin meanings.

> me: it is recognizing parts better
> me: but it is not enough
> me: At least for the boards i mentioned, let it know what each pin means
> AI: For Arduino Uno, ESP32 DevKit, 8085, PYNQ-Z2, Basys 3 and Boolean Board: what should knowing each pin's meaning do in the app? Note that the pin lists would come from the makers' official documents (I won't type them from memory), and none of this helps with an unseen interview board.
> (Label pins on the photo (Recommended) / Pin reference panel only / Name whole parts automatically)
> me: "Label pins on the photo (Recommended)"
> me: Let other be the optoin to choose those predetermined boards and allow us to teach it new boards for the interview

## Where the AI was wrong

- Its first Archify description drew the benchmark inside the running app. Archify's own check refused it.
- It drew the red result banner with red text on red. Found by looking at the page, not by a test.
- Its first evidence formula scored an empty patch as a perfect match. Tests written for the demo's failure modes caught that and three other faults the benchmark had not shown (commit "Tests for the demo's failure modes, and the fixes they forced").
- A web search summary told it a paper used image subtraction and YOLO. The paper's abstract does not say so, and the claim was left out.
- It first ran the preview from a folder macOS protects, and the app hung until it was run from elsewhere.
- Its own chat exporter would have shown the app's automatic summary of the conversation as a message from me.
- Its privacy check missed a GitHub account name in the exported chat. A wider scan caught it before the first push.
- It took the commit author from a name saved on this computer without asking me. On 25 November the author on every commit was corrected to mine, with files, dates and messages unchanged.
- It told me twice the repo was still private without checking. I had already made it public.
- It put the style for the new "Find all parts" button in a stylesheet the page does not load. It noticed before committing.
- When the new version did not show on the Windows laptop, it suggested the browser might be showing an old copy of the page. The app already tells browsers not to keep one. The real cause was a `git pull` that had stopped with an error.
- Its first "Find all parts" took the commonest colour in the middle of the photo to be the board. Every test board filled the frame, so the tests passed. On my first real photo, a board held in my hand over a paper bag and a tiled floor, it boxed things on the bag. It now picks the colour region with the most parts packed inside it, and a test with boards held small in a busy photo was added.
- The first draft of this file had two "pasted" excerpts that were not in the chat: one it wrote itself, and one paraphrased from its own notes with a wrong number. The excerpts above are copied from the exported chat.
