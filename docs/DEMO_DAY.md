# Demo day

## What to show (about 5 minutes)

1. **Lesson tab.** Type: *"I think if a star is ten times farther away it's ten times fainter."* Point out the stage tracker, the teaching plan you can open (a plan the model wrote, not its hidden reasoning), and the memory panel filling in after the reply. Answer its check-in question wrong on purpose and watch it mark you and note the misconception.
2. **Base vs fine-tuned tab.** Pick a held-out question and press *Ask both*. Same weights and prompt; the only difference is the adapter. The footer grades each final answer against the physics module.
3. **How it was built tab.** Scroll: comparison ratings → lessons generated → the filter funnel, with real rejected lessons and why they were rejected → dataset → loss curve and settings → eval result → the study, with its limits.

## Say this up front

The original code, data and adapter were deleted after the films were submitted. **This is a rebuild**: same method and settings, freshly generated and re-checked data, newly trained adapter. So:

- The participants in the study used the **original** tutor, not this one. The study numbers are the surviving group averages; nothing in the app re-creates them.
- Dataset counts, losses and the eval result shown are from **this rebuild**, read live from its output files.
- The base vs fine-tuned evaluation is new: it's the comparison the films said you'd do next.

Saying this first is far stronger than being caught out by a question about it.

## Checklist

- [ ] GPU pod running 30 minutes early; `make app` started; the first answer warms the model (about 1 minute)
- [ ] Classroom laptop opens the URL; test one message in each tab
- [ ] Click **New learner** so the memory panel starts empty
- [ ] Backup plan: screenshots of each tab, plus `outputs/eval/report.md`, in case the network fails
- [ ] Stop the pod afterwards
