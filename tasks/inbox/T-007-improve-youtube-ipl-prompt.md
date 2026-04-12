# YouTube IPL Fantasy Prediction Analysis Prompt

**Input:**
- Paste the YouTube video URL here: [YOUTUBE_URL]
- Paste the video transcript here (if available): [YOUTUBE_TRANSCRIPT]

**Objective:**
Analyze the provided YouTube video content concerning fantasy team predictions for an upcoming IPL match. Extract all actionable insights and recommendations presented by the creator.

**Instructions:**
1.  **Comprehensive Extraction:** Identify and extract all specific player recommendations, team compositions, and strategic advice mentioned in the video.
2.  **Toss Dependency:** Critically distinguish between pre-toss general recommendations and post-toss conditional recommendations. Explicitly detail how the toss outcome (e.g., winning the toss and choosing to bat or bowl) might influence team selection, captaincy, and vice-captaincy choices.
3.  **Key Information Extraction:** Extract the following specific details:
    *   **Likely Playing XI:** List the players most likely to be in the starting lineup for both teams.
    *   **Top Performer Candidates:** Identify players predicted to perform exceptionally well.
    *   **Captaincy Candidates:** List players recommended as captain choices.
    *   **Vice-Captaincy Candidates:** List players recommended as vice-captain choices.
    *   **Post-Toss Changes:** For each team, detail any specific player selection changes, captain/vice-captain swaps, or strategic adjustments that depend on winning the toss and the subsequent decision (batting first vs. bowling first).
4.  **Claim Verification:** Clearly categorize each piece of information as:
    *   **Confirmed Claim:** A direct statement made by the YouTuber.
    *   **Inferred Claim:** A logical deduction based on the YouTuber's statements, but not explicitly stated.
    *   **Uncertain Point:** A speculative suggestion or a point where the YouTuber expresses doubt.
5.  **Fidelity:** Do not invent any recommendations, player names, statistics, or strategic advice that is not present in the provided video content or transcript. If information for a category is not mentioned, state "Not mentioned."
6.  **Output Format:** Present the extracted information in a clear, concise, bullet-point format under the defined sections.

**Expected Output Structure:**

```
### Pre-Toss Recommendations:
*   **Likely Playing XI:**
    *   Team [Team Name 1]:
        *   [Player Name] - Role (e.g., Batsman, Bowler, All-rounder)
        *   ...
    *   Team [Team Name 2]:
        *   [Player Name] - Role
        *   ...
*   **Top Performer Candidates:**
    *   [Player Name] - Justification (e.g., "Good recent form", "Favorable matchup")
    *   ...
*   **Captaincy Candidates:**
    *   [Player Name] - Reason for recommendation
    *   ...
*   **Vice-Captaincy Candidates:**
    *   [Player Name] - Reason for recommendation
    *   ...

### Post-Toss Conditional Recommendations:
*   **If [Team Name 1] wins toss and chooses to bat:**
    *   Playing XI Changes: [List any changes, e.g., "Player X in, Player Y out"]
    *   Captaincy/Vice-Captaincy Changes: [List any changes, e.g., "Consider Player Z as captain"]
    *   Swap Logic: [Describe any specific player swaps based on this decision]
*   **If [Team Name 1] wins toss and chooses to bowl:**
    *   Playing XI Changes: [...]
    *   Captaincy/Vice-Captaincy Changes: [...]
    *   Swap Logic: [...]
*   **If [Team Name 2] wins toss and chooses to bat:**
    *   Playing XI Changes: [...]
    *   Captaincy/Vice-Captaincy Changes: [...]
    *   Swap Logic: [...]
*   **If [Team Name 2] wins toss and chooses to bowl:**
    *   Playing XI Changes: [...]
    *   Captaincy/Vice-Captaincy Changes: [...]
    *   Swap Logic: [...]

### Claim Categorization:
*   **Confirmed Claims:**
    *   [Statement 1]
    *   ...
*   **Inferred Claims:**
    *   [Inference 1]
    *   ...
*   **Uncertain Points:**
    *   [Uncertainty 1]
    *   ...
```