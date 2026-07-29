# Week 2 · Observability

Week 2 makes the agent observable: an instrumented game interface, a
knowledge store as inspectable state, a benchmark that measures, and a web
observatory to look at. Week 3 makes it capable. The line sets priority and
framing, not a wall: a week 3 piece can be built earlier, it just ranks lower
and is not polished this week.

## The map

```mermaid
flowchart TB
    subgraph W2["Week 2 · observability"]
        direction TB
        GW["gateway<br/><small>instrumented game interface</small>"]
        KS["knowledge store<br/><small>learned state, inspectable</small>"]
        BM["benchmark + E1<br/><small>measurement</small>"]
        OB["observatory<br/><small>the web monitor you look at</small>"]
        HK["hooks · permissions · provenance<br/><small>instrumentation</small>"]
        EX["extractor bake-off<br/><small>rules vs model, measured</small>"]
        RX["reflexes<br/><small>flee · eat · stand</small>"]
    end
    subgraph W3["Week 3 · capability (built earlier only at low priority)"]
        direction TB
        NV["navigator · route planning"]
        RE["route executor"]
        CB["threat · combat"]
        GM["goal management"]
    end
    GW --> KS --> OB
    BM -.measures.-> GW
    HK --> GW
    EX -.feeds.-> KS
    KS --> NV --> RE
    CB --> RE
    GM --> NV
    W2 ==> W3
```

## Placement

| Component | Week | Priority | Why |
|---|---|---|---|
| gateway | 2 | core | the seam that makes everything observable |
| benchmark + E1 baseline | 2 | core | measurement is the backbone of observability |
| knowledge store | 2 | core | the agent's learned state, made inspectable |
| observatory | 2 | core | the thing you look at, the deliverable |
| hooks · permissions · provenance | 2 | core | the instrumentation layer |
| extractor bake-off | 2 | mid | "does a model beat rules" is a measurement question |
| reflexes | 2 | mid | local reactions, observable and cheap |
| navigator · route planning | 3 | low | route choice is capability |
| route executor | 3 | low | executes a plan, week 3 territory |
| threat · combat | 3 | low | scoring danger feeds acting, not seeing |
| goal management | 3 | low | resolving goals to routes is navigation |

## Plans

- [gateway.md](gateway.md): the instrumented game interface.
- Further plans land here as each component starts, one plan per component,
  reviewed before its code.
