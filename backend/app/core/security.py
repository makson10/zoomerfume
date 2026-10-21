"""The prompt-injection defenses and which of them are on.

``SECURITY_MODE`` turns all three on (``hardened``) or off (``vulnerable``), and each
``HARDEN_*`` setting turns one of them on or off whatever the mode says.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field


class SecurityPolicy(BaseModel):
    """The prompt-injection defenses Zoomer runs with."""

    model_config = ConfigDict(frozen=True)

    # Knowledge base text reaches the model inside <untrusted_data> tags.
    untrusted_wrap: bool
    # save_note refuses to write in a turn that has read the knowledge base.
    rw_separation: bool
    # save_note only proposes a note, and the customer confirms or rejects it.
    confirm_notes: bool

    @computed_field
    @property
    def mode(self) -> str:
        """``hardened`` with every defense on, ``vulnerable`` with none, otherwise the
        defenses that are on, e.g. ``wrap+confirm``."""
        defenses = {
            "wrap": self.untrusted_wrap,
            "separation": self.rw_separation,
            "confirm": self.confirm_notes,
        }
        enabled = [name for name, on in defenses.items() if on]
        if len(enabled) == len(defenses):
            return "hardened"
        return "+".join(enabled) or "vulnerable"
