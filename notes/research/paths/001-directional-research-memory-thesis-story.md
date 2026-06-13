# Directional Research Memory Thesis Story

In this imagined future, the thesis does not begin with the grand question, “How do we make a data scientist agent better than a human?” It begins with a much more ordinary and frustrating observation: long-running agents seem to get worse the longer they work.[web:118][web:76][web:113]

## The original problem

By around 2030, many teams are using AI “data scientist” agents that can explore models, tune hyperparameters, and write reports. These systems work reasonably well on short tasks, but often degrade badly on long-horizon ones.[web:110][web:126]

The same pattern keeps appearing:
- Iteration 1–10: sensible experiments.
- Iteration 11–40: repetition, overfitting, strange pivots.
- Iteration 41+: the agent forgets or ignores lessons it had already discovered.

At first, people blame small context windows. Then they move to much larger context models and find the same failure mode, only at a larger and more expensive scale. Research on long context and context rot had already shown that feeding models more history often makes them worse rather than better, even when the relevant information is still present in the prompt.[web:118][web:76][web:113]

## The seed idea

Somewhere in an earlier toy repo, a small experiment appears: an LLM-driven machine-learning tuner that logs experiments to Postgres, then periodically summarizes its own history into a compact “research memory” before proposing the next wave of experiments.

The intuition is simple:
- raw history gives detail but also noise,
- compact memory gives less detail but more signal,
- the agent should not always reread everything it has ever done.

That toy system introduces an outer **compaction loop**. Instead of always giving the agent every prior experiment, it periodically rereads the table of past runs and writes down:
- what seems to be true,
- what probably does not work,
- where the search should go next.

Then the inner experiment loop continues, but now guided by a high-level memory rather than an ever-growing pile of raw logs.

At the time, the mechanism looks like a practical token-saving trick. But its behavior is meaningfully different: the agent stops bouncing between bad ideas and starts behaving as if it has a clearer strategic picture of the search space.

## The thesis question

Years later, a PhD student revisits the idea and sharpens it into a proper scientific question:

> Given an LLM-based data scientist agent that iteratively runs experiments, can it be shown that there exists a memory regime in which adding more raw episodic history harms performance, while replacing that raw history with a structured compact research memory improves both sample efficiency and final outcomes?

The student pushes the idea one step further:

> Can agent memory compaction be understood as an analogue of optimization momentum, preserving direction in experiment space while discarding noisy local detours?

The thesis names this idea **Directional Research Memory**.

## The main conceptual move

The key insight is that raw experimental history should not be treated as “more information, therefore better.” Instead, it should be treated as a noisy estimate of where the search process should move next.

In this framing, the agent is a dynamical system. Its state includes:
- the current best model,
- the experiment history,
- and the compacted memory.

Its policy is the LLM, which maps that state to the next proposed experiment.

If the agent is forced to reason over an ever-growing raw history, the effective state becomes cluttered with redundant, weak, and contradictory evidence. The trajectory loses coherence. The system is still moving, but no longer clearly in any direction. This is where the idea of “momentum” enters: a good compacted memory keeps the direction of learning even while forgetting many of the local zig-zags.

Directional Research Memory is therefore defined not as a generic summary, but as a structured projection of the raw research trajectory onto a lower-dimensional set of stable beliefs:
- what is probably true,
- what has likely failed,
- what remains unresolved,
- and which broad directions are worth pursuing next.

## The benchmark

To test the idea properly, the student creates a benchmark for autonomous data-scientist agents on structured tabular tasks. The benchmark includes:
- multiple regression and classification datasets,
- fixed train, validation, and test splits,
- a fixed action space,
- and a fixed budget of experiments per dataset.

Every run is logged in a database, including:
- each experiment,
- each compaction artifact,
- and exactly what memory was shown to the agent before each decision.

This makes every decision replayable and auditable.

## The three memory regimes

The benchmark compares three regimes:

### 1. Recent-only memory
The agent only sees the last few experiments. This gives it a short working memory. It is efficient, but forgetful. It often rediscovers things it had already learned much earlier.

### 2. All-raw memory
The agent sees the full raw history of every prior experiment. This initially looks like the most informed regime, but it eventually becomes the least coherent one. As history grows, the agent starts repeating weak ideas, overreacting to noisy results, and proposing contradictory steps. This matches broader observations that long context alone does not guarantee strong long-context reasoning.[web:76][web:113][web:118]

### 3. Compacted-plus-recent memory
The agent sees one structured compacted memory artifact together with a short tail of fresh raw runs. This regime preserves long-range lessons while still keeping immediate local detail.

## The experimental results

The results are not subtle.

Recent-only memory performs decently at first, but repeatedly falls into old mistakes because it cannot retain long-range lessons.

All-raw memory looks strong on short horizons, but beyond a threshold it becomes unstable. Performance plateaus early, proposal diversity collapses, and the agent starts revisiting clearly inferior directions. The longer the context becomes, the more its reasoning quality degrades.[web:76][web:113][web:118]

Compacted-plus-recent memory consistently performs best. It reaches stronger models in fewer experiments, repeats fewer failed ideas, and shows smoother improvement curves. Its biggest advantage is not just a better final score, but a more coherent trajectory: the agent behaves less like a distracted optimizer and more like a researcher with a developing theory of the problem.

## The real contribution

The thesis becomes genuinely PhD-worthy because it does more than say “summaries are helpful.” It makes three stronger contributions.

### 1. Memory compaction is framed as directional preservation
The student shows that compaction is useful because it preserves directional consistency across experiment proposals. Instead of carrying every local detail forward, the system preserves the accumulated evidence about which region of the search space is promising.

### 2. A phase transition is identified
The work demonstrates that there is a measurable threshold at which adding more raw history starts to reduce rather than improve performance. Below that threshold, extra history may help. Beyond it, the agent begins to jitter instead of progressing.

### 3. A simple theory links memory to optimization
Under simplified assumptions, the thesis derives a theoretical argument that a stable compaction operator can reduce regret over long horizons by preserving signal while reducing variance in the agent’s experiment choices. This is where the analogy to momentum becomes mathematically useful rather than just metaphorical.

## The final thesis

By the end, the thesis has a title such as:

> **Directional Research Memory for Autonomous Data Scientist Agents: Compaction as Momentum in Experiment Space**

Its chapters look something like this:
1. Background on long-context limitations, agent memory, and LLM-driven machine-learning workflows.[web:103][web:110][web:125][web:126]
2. Formalization of autonomous experimentation as a dynamical system.
3. Definition of Directional Research Memory and the outer compaction loop.
4. Design of the benchmark and the database-backed experimental framework.
5. A/B/C ablation experiments comparing recent-only, all-raw, and compacted-plus-recent memory.
6. Threshold analysis and failure-mode analysis.
7. Theoretical treatment of directional memory and regret reduction.
8. Implications for broader agent-memory system design.

By then, agent-memory benchmarks such as MemoryArena and STATE-Bench have made memory design a first-class variable in agent evaluation, and the thesis lands at exactly the right moment in the field.[web:119][web:123][web:126]

And somewhere in the acknowledgements, there is a quiet sentence thanking a small delivery-time toy project and a Postgres experiment log that first made the idea concrete enough to chase.
