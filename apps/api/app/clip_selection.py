"""Bounded diversity over already valid complete-sentence source windows.

No language model, semantic quality score or change to source ranges. Selection
compares existing technical scores and temporal overlap only.
"""
ALGORITHM='sentence-window-v4-diverse-reviewed'


def overlap(left,right):
    intersection=max(0,min(left.source_end_ms,right.source_end_ms)-max(left.source_start_ms,right.source_start_ms))
    union=max(left.source_end_ms,right.source_end_ms)-min(left.source_start_ms,right.source_start_ms)
    return intersection/union if intersection else 0.0


def diverse(candidates):
    remaining=list(candidates)
    selected=[]
    while remaining and len(selected)<5:
        eligible=[candidate for candidate in remaining if all(overlap(candidate,old)<.85 for old in selected)]
        if not eligible:break
        def order(candidate):
            similarity=max((overlap(candidate,old) for old in selected),default=0.0)
            # Keep the strongest technical option first, then give other source
            # regions a chance. Stable time/word tie-breaks make replay exact.
            return (-(candidate.score-.35*similarity),candidate.source_start_ms,
                    candidate.source_end_ms,candidate.first_word,candidate.last_word)
        best=min(eligible,key=order);selected.append(best);remaining.remove(best)
    return selected
