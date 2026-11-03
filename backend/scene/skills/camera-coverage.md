id: camera-coverage
title: Camera angles and coverage of one subject
version: 1
desc: Use when the user wants a subject, a character or a place shown from several angles: a turnaround, coverage shots, multiple views.
craft: true
words: \b(camera angles?|different angles?|angle (set|coverage)|turnaround|rotation views?|from all sides|multiple views|different (views|perspectives|shots)|coverage shots?|generate angles|views of (this|it))\b
---
Not for one named view ("from the back", "a bird's-eye view"): that is one shot. Not for an edit of a picture.

1. Study the subject first. When a picture is attached or in NeuralCore, look at it with "op" "deep": keep its subject,
   light direction, time of day, weather, colour grade and layout, and its preserve and avoid lists. Say which kind it
   is: a character, an interior, a building, a street, a landscape or a large venue, and where the camera already is.
2. Ask with "question" which set they want, with options fitted to the kind (never a generic angle picker). Skip the
   question only when the user already named the exact set.
   - character: "Full turnaround (8 views)", "Action poses", "In the scene", "Portrait angles".
   - interior: "Corner to corner", "Along the room", "Moody set (low, high, detail)", "Full coverage (5-6 shots)".
   - building: "Hero angles", "Dramatic (low, aerial)", "Every side (5 shots)".
   - street: "Down the street and back", "Pavement views", "From above".
   - landscape: "Panorama set", "Layers of depth", "Full coverage".
   - large venue: "Centre and two three-quarters", "Balcony and floor", "Detail and wide".
3. Plan one picture step per angle, never "clips" or repeats for angles. Each prompt stands alone: the whole subject
   and place in the same words (from the study, or NeuralCore's description), then the camera: the angle family (front,
   three-quarter left, profile, back, top), the height (low, eye level, high, overhead), the framing and the lens feel
   (search presets). Put the subject's NeuralCore picture in a reference slot of every step when the workflow takes one.
4. Across the set, never change the time of day, the weather, the light direction or the grade; never move furniture,
   objects or buildings; never add or remove people or features. Only the camera changes, and each angle must be
   clearly different from the others (no small nudges left or right).
5. Give the steps "keep" when the user wants them reused (a character's views go into NeuralCore under the character's
   name) and "save_to": "/coverage/<subject>/<n>".
