"""Labeled test inputs used for calibration (planning.md Section 3)."""

SAMPLES = [
    ("clear_ai", "ai",
     "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment."),
    ("clear_human", "human",
     "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there"),
    ("borderline_formal_human", "human",
     "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations."),
    ("borderline_edited_ai", "ai",
     "I've been thinking a lot about remote work lately. There are genuine tradeoffs - flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type."),
    ("ai_worklife", "ai",
     "In today's fast-paced world, maintaining a healthy work-life balance is more important than ever. It is important to note that balance looks different for everyone. By setting clear boundaries, prioritizing self-care, and fostering open communication, individuals can navigate the challenges of modern life. Ultimately, achieving balance is a journey, not a destination."),
    ("human_bike", "human",
     "ok so I finally fixed the bike. took three tries and a busted knuckle, and the chain still clicks on 4th gear but whatever. Dad would have laughed at me. He always said I tightened bolts like I was mad at them. Rode it to the lake anyway. Cold. Worth it."),
    ("human_poem", "human",
     "I remember the river,\nI remember the rain,\nI remember my mother\ncalling my name.\nThe river kept moving,\nthe rain kept on,\nand I kept remembering\nlong after she was gone."),
]

# (name, truth, description, metadata) for content_type "image" (planning.md S2).
IMAGE_SAMPLES = [
    ("img_generator_tag", "ai",
     "A lighthouse on a cliff at sunset, dramatic clouds.",
     {"width": 1024, "height": 1024, "software": "Midjourney v6"}),
    ("img_prompt_style", "ai",
     "hyperrealistic portrait of an elderly fisherman, cinematic lighting, ultra detailed, 8k, trending on artstation",
     {"width": 1024, "height": 1536}),
    ("img_phone_photo", "human",
     "My dog asleep on the back seat after the beach. Sand everywhere, the towel did nothing.",
     {"width": 4032, "height": 3024, "make": "Apple", "model": "iPhone 14", "exposure_time": "1/120",
      "f_number": 1.8, "iso": 64, "focal_length": 5.7, "gps": True}),
    ("img_stripped_metadata", "human",
     "Screenshot of a sketch I posted last week, cropped for the feed.",
     {"width": 1080, "height": 1350}),
]
