# MBA Summer Eligibility
> Use when deciding whether a posting is a summer internship an MBA student can apply to, and how to set mba_eligible.

**mba_eligible** (Yes / No / Not clear, from the text only)
- "Yes": the text says MBA students, graduate students, or a named MBA program (for example "MBA Summer Associate", "currently enrolled in an MBA program") are eligible.
- "No": the text excludes them, for example undergraduates only, a bachelor's degree in progress required, or PhD only. A graduation window the student misses is a timing mismatch for `fit`, not "No".
- "Not clear": anything else. Generic "students" or "interns" without a degree level is "Not clear", never "Yes".

**Is it a summer internship?**
- Count it when the text names a summer program, a summer start, or a fixed internship of a set length over the summer.
- Not a summer internship: full-time roles, fall or spring co-ops, part-time term-time roles, "talent community" sign-ups. Say which in `key_points` or `fit_reason`.
- Timing must match the summer the student is recruiting for (from the profile). If the profile does not say, timing is unknown: put it in `fields_not_found`.

**formal_internship**
- "Yes" only for a structured program (named program, cohort, stated length or start).
- A one-off "intern" opening with no program details: "Not clear".

**Always**
- Quote the eligibility sentence exactly as `evidence` or add it to `key_points`.
- Never infer eligibility from reputation or past cycles.
