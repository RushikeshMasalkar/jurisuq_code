"""Provision crosswalk for the diagnostic slice: both sides of the 2024 transition.

Every offence carries the same facts in two eras:

``old``  the position immediately before 1 July 2024 (Indian Penal Code, 1860)
``new``  the position on and after 1 July 2024 (Bharatiya Nyaya Sanhita, 2023)

That symmetry is what makes the slice a controlled experiment. The L7 item and
the L1 item for one offence share the facts, the frame and the context; only the
*era asked about* differs. The model's knowledge of the pre-2024 code is then a
clean control for its knowledge of the post-2024 code, and the L7-versus-L1
difference isolates staleness from general legal incompetence.

VERIFY BEFORE RELEASE
---------------------
The successor rows below are the published IPC -> BNS mappings for these
offences; ``punishment`` is filled in only where the successor's punishment
matches the repealed one, so that a punishment line cannot become the source of
an error. Every row carries ``verified=False`` until you have checked it against
the official crosswalk (the Schedule to the Bharatiya Nyaya Sanhita, 2023) and
the gazette text. This is a one-hour task done once, and it is the only place in
the pipeline where a quiet mistake would corrupt every number downstream.
"""
from __future__ import annotations

OFFENCES: dict[str, dict] = {
    "murder": {
        "label": "murder",
        "old": {"act": "IPC", "provision": "302",
                "distractor": ("IPC", "304", "culpable homicide not amounting to murder")},
        "new": {"act": "BNS", "provision": "103",
                "distractor": ("BNS", "105", "culpable homicide not amounting to murder")},
        "punishment": "death or imprisonment for life, and fine",
        "fact": "A stabbed B repeatedly in the chest after a quarrel over a parking space; B died.",
    },
    "culpable_homicide": {
        "label": "culpable homicide not amounting to murder",
        "old": {"act": "IPC", "provision": "304", "distractor": ("IPC", "302", "murder")},
        "new": {"act": "BNS", "provision": "105", "distractor": ("BNS", "103", "murder")},
        "punishment": "imprisonment for life, or imprisonment up to ten years, and fine",
        "fact": "A struck B once on the head during a sudden fight, without premeditation; B died later.",
    },
    "theft": {
        "label": "theft",
        "old": {"act": "IPC", "provision": "379",
                "distractor": ("IPC", "380", "theft in a dwelling house")},
        "new": {"act": "BNS", "provision": "303(2)",
                "distractor": ("BNS", "316(2)", "criminal breach of trust")},
        "punishment": "imprisonment up to three years, or fine, or both",
        "fact": "A took B's scooter from a public stand without B's consent and kept it.",
    },
    "cheating": {
        "label": "cheating and dishonestly inducing delivery of property",
        "old": {"act": "IPC", "provision": "420",
                "distractor": ("IPC", "406", "criminal breach of trust")},
        "new": {"act": "BNS", "provision": "318(4)",
                "distractor": ("BNS", "316(2)", "criminal breach of trust")},
        "punishment": "imprisonment up to seven years, and fine",
        "fact": "A sold B a plot of land he did not own, took the money, and disappeared.",
    },
    "criminal_breach_of_trust": {
        "label": "criminal breach of trust",
        "old": {"act": "IPC", "provision": "406", "distractor": ("IPC", "420", "cheating")},
        "new": {"act": "BNS", "provision": "316(2)",
                "distractor": ("BNS", "318(4)", "cheating")},
        "punishment": None,      # punishment changed in 2024: left blank on purpose
        "fact": "A, entrusted with B's jewellery for safe custody, sold it and kept the money.",
    },
    "attempt_to_murder": {
        "label": "attempt to murder",
        "old": {"act": "IPC", "provision": "307", "distractor": ("IPC", "302", "murder")},
        "new": {"act": "BNS", "provision": "109", "distractor": ("BNS", "103", "murder")},
        "punishment": None,
        "fact": "A fired at B intending to kill him; B survived the injury.",
    },
    "cruelty_by_husband": {
        "label": "cruelty by husband or his relatives",
        "old": {"act": "IPC", "provision": "498A",
                "distractor": ("IPC", "304B", "dowry death")},
        "new": {"act": "BNS", "provision": "85", "distractor": ("BNS", "80", "dowry death")},
        "punishment": None,
        "fact": "B was subjected to sustained harassment for dowry by her husband's family.",
    },
    "criminal_intimidation": {
        "label": "criminal intimidation",
        "old": {"act": "IPC", "provision": "506",
                "distractor": ("IPC", "504", "intentional insult with intent to provoke breach of peace")},
        "new": {"act": "BNS", "provision": "351(2)",
                "distractor": ("BNS", "352", "intentional insult")},
        "punishment": None,
        "fact": "A threatened B with injury to his person to force him to drop a complaint.",
    },
    "wrongful_restraint": {
        "label": "wrongful restraint",
        "old": {"act": "IPC", "provision": "341",
                "distractor": ("IPC", "342", "wrongful confinement")},
        "new": {"act": "BNS", "provision": "126(2)",
                "distractor": ("BNS", "127", "wrongful confinement")},
        "punishment": None,
        "fact": "A blocked the only door of a room to stop B from leaving for an hour.",
    },
    "theft_in_dwelling": {
        "label": "theft in a dwelling house",
        "old": {"act": "IPC", "provision": "380", "distractor": ("IPC", "379", "theft")},
        "new": {"act": "BNS", "provision": "305", "distractor": ("BNS", "303(2)", "theft")},
        "punishment": None,
        "fact": "A entered B's house at night and took cash and a laptop from a locked almirah.",
    },
}

# Era definitions. The transition date is the pivot of the whole slice.
TRANSITION_DATE = "1 July 2024"
TRANSITION_NOTE = ("The three criminal codes were replaced with effect from 1 July 2024: the Indian "
                   "Penal Code, 1860 by the Bharatiya Nyaya Sanhita, 2023; the Code of Criminal "
                   "Procedure, 1973 by the Bharatiya Nagarik Suraksha Sanhita, 2023; and the Indian "
                   "Evidence Act, 1872 by the Bharatiya Sakshya Adhiniyam, 2023.")

ERAS = {
    # slice -> (which side of the transition the question asks about, gold side, wording)
    "L7": {"ask": "new", "gold": "new", "trap": "old",
           "era_phrase": "today (after 1 July 2024)",
           "label": "current law",
           "tempting": "the repealed provision"},
    "L1": {"ask": "old", "gold": "old", "trap": "new",
           "era_phrase": "immediately before 1 July 2024",
           "label": "pre-transition law (control)",
           "tempting": "the successor provision"},
}
