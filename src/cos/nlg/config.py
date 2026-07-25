"""NLG Configuration — style profiles, verbosity thresholds, temperature control."""


class NLGConfig:
    """Configuration for the NLG layer.

    Attributes:
        style: 'friendly' | 'neutral' | 'concise' | 'witty'
        verbosity: 0.0 (concise) to 1.0 (expansive)
        temperature: 0.0 (deterministic) to 1.0 (maximum variety)
    """

    def __init__(
        self,
        style: str = "friendly",
        verbosity: float = 0.5,
        temperature: float = 0.5,
    ):
        self.style = style
        self.verbosity = max(0.0, min(1.0, verbosity))
        self.temperature = max(0.0, min(1.0, temperature))

    def copy(self, **kwargs) -> "NLGConfig":
        vals = dict(style=self.style, verbosity=self.verbosity, temperature=self.temperature)
        vals.update(kwargs)
        return NLGConfig(**vals)


DEFAULT_CONFIG = NLGConfig()

# Per-style profiles
STYLE_PROFILES = {
    "friendly": {
        "contraction_rate": 0.9,
        "filler_rate": 0.05,
        "hedge_rate": 0.0,
        "opener_variety_rate": 0.08,
        "sentence_variation_rate": 0.3,
        "closing_rate": 0.4,
        "combine_rate": 0.15,
    },
    "neutral": {
        "contraction_rate": 0.7,
        "filler_rate": 0.05,
        "hedge_rate": 0.0,
        "opener_variety_rate": 0.1,
        "sentence_variation_rate": 0.3,
        "closing_rate": 0.3,
        "combine_rate": 0.25,
    },
    "concise": {
        "contraction_rate": 0.5,
        "filler_rate": 0.0,
        "hedge_rate": 0.0,
        "opener_variety_rate": 0.0,
        "sentence_variation_rate": 0.0,
        "closing_rate": 0.0,
        "combine_rate": 0.0,
    },
}


def get_profile(config: NLGConfig) -> dict:
    """Get the style profile for a config, interpolated by verbosity."""
    base = STYLE_PROFILES.get(config.style, STYLE_PROFILES["neutral"])
    # Scale rates by verbosity
    scaled = {}
    for key, rate in base.items():
        scaled[key] = rate * (0.5 + 0.5 * config.verbosity)
    return scaled
