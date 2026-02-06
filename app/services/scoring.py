def calculate_score(questions, answers):
    score = 0
    for question, answer in zip(questions, answers):
        if not question:
            continue
        if answer and answer == question["correct"]:
            score += 1
    return score
