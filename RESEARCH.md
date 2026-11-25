# Research

What was looked at before choosing, what was compared, and what was rejected.
Sources marked † were read for this project (November 2026). Others are named
from general knowledge and were not re-read.

## The question

One photo of a good board, boxes named by the user, then photos of the same
board from a fixed camera. The board at the demo is unseen, so whatever is
chosen has to work with **one example and no training**.

## Existing tools and papers

| Source | What it does | Why it is or is not the answer |
|---|---|---|
| [rolandwa/aoi](https://github.com/rolandwa/aoi) † | DIY inspection of assembled boards: golden sample, alignment, optional YOLO and OCR, reads Gerber and BOM. GPL-3.0, 6 commits. | Closest in spirit. Confirms the golden-sample idea. It wants design files a shop-floor user will not have. No code used. |
| [PCB-Fire, arXiv 2102.10777](https://arxiv.org/abs/2102.10777) † (abstract) | Missing-component detection with "pixel theory and object detection". | A trained detector only knows the parts it was trained on. |
| [PatchCore, arXiv 2106.08265](https://arxiv.org/abs/2106.08265) † (abstract) | Memory bank of features from good images; up to 99.6% image AUROC on MVTec AD. | Built for a set of good images. We have one. Finds "something odd", not "which named part". |
| [AnomalyDINO, arXiv 2405.14529](https://arxiv.org/abs/2405.14529) † (abstract) | DINOv2 patch features, no training, one good image. One-shot MVTec AD AUROC 93.1% to 96.6%. | The strongest candidate that was **not** tested. See below. |
| [anomalib](https://github.com/open-edge-platform/anomalib) † | Apache-2.0 library of anomaly methods, PatchCore included. | Heavy for this job, same limits as PatchCore. |
| Commercial AOI machines | Golden board plus per-part windows drawn by an engineer. | The workflow the brief describes. The app copies it: one reference, one window per part. |

## Data sources

| Source | Content | Used? |
|---|---|---|
| [VisA](https://github.com/amazon-science/spot-diff) † | 4 PCB types, about 1,000 good and 100 bad photos each, missing parts among the defects. Data CC BY 4.0. | Best public fit. **Not downloaded** for this project. First thing to add. |
| [PCB-DSLR](https://cvl.tuwien.ac.at/research/cvl-databases/pcb-dslr-dataset/) † | 748 photos of 165 boards, boxes for ICs only. Non-commercial research use. | No. No missing parts, small parts not labelled. |
| [DeepPCB](https://github.com/tangsanli5201/DeepPCB) † | 1,500 template/test pairs: opens, shorts, mouse bites. | No. Trace defects, not parts. |
| Own generator, [bench/synth.py](bench/synth.py) | Boards drawn from a seed in 7 colours and 13 part types. Any part can be left off, with its pads or wiped clean. A camera model adds shift, tilt, uneven light, shadow, glare, blur, noise, JPEG, and the drift of an AI image editor. | **Yes.** The answer is known exactly, so every claim below is measured. |

**The honest gap:** all measurements are on drawn boards. Nothing here has been
measured on real photographs or on real AI-edited images.

## Options compared

Same boxes, same photos, thresholds set on the training boards only. Details,
and the result by part type and board colour, in [bench/RESULTS.md](bench/RESULTS.md).

| Method | AUC | Missed | False alarms | Photos fully right | easy | line | redraw | harsh |
|---|---|---|---|---|---|---|---|---|
| Pixel difference, as taken | 0.8181 | 92 of 602 | 2902 of 7014 | 20.4% | 78% | 1% | 3% | 0% |
| Pixel difference, aligned | 0.9628 | 34 of 602 | 1053 of 7014 | 49.8% | 93% | 63% | 41% | 2% |
| SSIM, aligned | 0.9965 | 6 of 602 | 395 of 7014 | 69.4% | 98% | 97% | 35% | 48% |
| Template match (NCC), aligned | 0.9990 | 7 of 602 | 94 of 7014 | 82.9% | 100% | 97% | 61% | 74% |
| This app without alignment | 0.9795 | 29 of 602 | 844 of 7014 | 64.6% | 98% | 72% | 88% | 1% |
| This app plus light matching (dropped) | 0.9999 | 8 of 602 | 7 of 7014 | 97.3% | 100% | 100% | 98% | 91% |
| This app without the bare-board vote | 1.0000 | 4 of 602 | 3 of 7014 | 98.8% | 100% | 100% | 99% | 96% |
| This app | 1.0000 | 8 of 602 | 2 of 7014 | 98.1% | 100% | 100% | 98% | 94% |

The app's shipped three-way verdict on the same 480 unseen photos:

| | said present | said check by eye | said missing |
|---|---|---|---|
| really present | 6983 | 30 | 1 |
| really missing | 1 | 21 | 580 |

Two results that do not flatter the design: on the final boards the app scored slightly
better *without* the bare-board vote (98.8% against 98.1% of photos), although on the
development boards it was the other way round (97.8% against 98.1%). The final set was run
once, so nothing was changed because of it. And 8 of the 10 two-way errors are black
chips on black boards, which is the known weak spot.

### Black parts on black boards

A second practice set was drawn only for this: 40 black boards (2000 to 2039), 320
photos, 5,208 part checks, 377 missing ([bench/dark_boards.py](bench/dark_boards.py)).
The app as shipped gives 1 wrong answer. It sends 82 parts (1.6%) to check by eye, 49
of them really missing. 52 of the 82 are in redrawn photos.

Many of the missing small parts score as "not bare board". A black body on a black board
cannot vote, so only the silver pads do, and pads stay when a part goes. Letting
only the middle of each box vote ([bench/core_vote.patch](bench/core_vote.patch)),
refitted on the same training boards, gives:

| | Black boards: wrong | Black boards: check by eye | Development photos fully right |
|---|---|---|---|
| As shipped | 1 | 82 | 98.1% |
| Only the middle votes | 0 | 85 | 98.4% |

That is one answer, three checks and one photo, too little to replace a method
that was already frozen and scored on the final boards. It was not adopted.

## What was picked and why

Align, measure each named part, judge the difference against the photo's own
noise, decide with a 7-weight model. It beats the simple methods where they
break (light, redrawn texture), runs on a CPU, and can say why.

## What was tried and dropped, or rejected

- **Pixel difference.** Useless without alignment, and alarmed by any change of light even with it.
- **SSIM.** Good until texture changes: an AI redraw sets it off everywhere.
- **Template matching.** The best simple method and the real competitor. It cannot tell "printed text changed" from "part gone".
- **Global light matching.** Built, measured, removed. It looked essential and made results worse once each part was corrected by the ring of board around it. The code stays in [bench/dropped_light.py](bench/dropped_light.py) so the row above can be reproduced.
- **Raw differences as features.** Replaced by ratios to a noise floor: a difference of 0.12 is damning in a clean photo and ordinary in a blurred one.
- **YOLO or another trained detector.** Needs labelled examples of these parts. There are none, and the demo board is unseen.
- **Asking a vision language model.** Not allowed (offline), and not repeatable.

## Not tested: DINOv2

AnomalyDINO suggests DINOv2 features would cope well with redrawn textures. Its
weights were not downloaded for this project, so no claim is made about
which is better. The benchmark is built so that it can be added as one more
column: score each box in `bench/dataset.py` and refit.

## How the numbers were kept honest

- Boards are split by seed: 100 to 139 fit the weights, 500 to 539 were looked at while designing, 900 to 959 were run once after the design was frozen.
- The `harsh` light level is never used for fitting.
- Boxes are drawn sloppily on purpose, and only some parts are named, as a person would.
- Boards 2000 to 2039 are practice only, drawn after the final run to study black boards. Nothing in the app was changed because of them.
- Before the freeze, a first version of the benchmark had no separate final set. Its test boards had been looked at, so they were demoted to development boards.
