def find_weak_tags(questions, answers, limit=3):
    counts = {}
    for question, answer in zip(questions, answers):
        if not question:
            continue
        if answer != question["correct"]:
            tag = question["concept_tag"]
            counts[tag] = counts.get(tag, 0) + 1

    sorted_tags = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [tag for tag, _count in sorted_tags[:limit]]
