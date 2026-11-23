FlyPoker V39 — HEADLESS + BRAIN MONITOR + HALL OF FAME + BALANCED REWARD

Install minimum (no screens): python -m pip install numpy
Install brain monitor: python -m pip install numpy opencv-python
Install all old modes: python -m pip install -r requirements.txt

1) FAST HEADLESS (no Pygame, no OpenCV, no Unity):
   python main.py --headless --generations 100 --hands 5000

2) ONLY BRAIN MONITOR (OpenCV, no Pygame):
   python main.py --brain-monitor --generations 5 --hands 200

3) UNITY AND NO PYGAME:
   python main.py --unity --headless --generations 10 --hands 200
   Unity waits for animation_done; this mode is not as fast as pure headless.

4) EXISTING PYGAME + BRAIN MONITOR:
   python main.py --render --render-every 1 --generations 5 --hands 200

5) WATCH BEST NO TRAINING:
   python main.py --watch-best --brain-monitor --hands 100

6) RESUME FROM BEST EVER:
   python main.py --resume-best --headless --generations 25 --hands 1000

7) LIST SAVED BEST FLIES:
   python main.py --list-best

Optional: --reward-mode classic restores previous fitness (raw bb/100 minus bust).
If changing reward weights across experiments, fitness values may not be directly comparable.
For a clean separate leaderboard, move/rename the existing checkpoints/hall_of_fame folder.
Use --brain-monitor only for live observation: it reduces simulation speed.
For maximum training speed use --headless without --unity.
--progress-every 500 prints progress; use 0 to disable.
Balanced: fitness = raw bb/100 + (table wins * win-bonus-bb *100/hands)
                    - (busts * bust_penalty_bb *100/hands)
                    - (risk-penalty * RMS(negative single-hand BB returns))
Default win bonus 2BB, risk penalty 0.25. This is a small risk preference,
NOT solver/GTO, NOT per-action RL and NOT calibrated poker equity.
No premature elimination on all-in: busts counted only AFTER hand payout.

Checkpoints:
  checkpoints/best_brain_gen_XXXX.npz  (all generations; untouched)
  checkpoints/hall_of_fame/balanced/leaderboard.json
  checkpoints/hall_of_fame/balanced/best_ever.npz
  checkpoints/hall_of_fame/balanced/gen_XXXX_fly_Y.npz (Top 5)
  checkpoints/training_history.jsonl  (persistent stats per generation)

Monitor: MLP real activations, action probability bars, top 3 choices,
normalized policy entropy and recent policy-concentration sparkline. The
anatomical backdrop is a VISUAL PROJECTION, not a 166k-neuron fly connectome.
The 'probability' is masked action softmax, NOT chance of winning a hand.

Python files only. No Unity C# changes needed. Use V38 bridge and scene.
Work from Python project folder so checkpoints/ appears there.
