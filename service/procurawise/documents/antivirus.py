from dataclasses import dataclass
from typing import Protocol

# The industry-standard EICAR antivirus test string (not malware itself - a
# harmless string every real antivirus engine is specifically built to
# detect, used worldwide to test AV integrations without handling real
# malicious content). Fase 16: the stub scanner flags any upload whose bytes
# contain this signature as infected, and only that - deterministic,
# testable, and realistic (a real scanner swapped in later would also flag
# it), without pretending to be a real malware engine.
EICAR_SIGNATURE = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@dataclass(frozen=True)
class ScanResult:
    clean: bool


class AntivirusScanner(Protocol):
    def scan(self, content: bytes) -> ScanResult: ...


class StubAntivirusScanner:
    """Fase 16 backlog: "escaneo AV stub". Synchronous, in-process - no
    quarantine pipeline, no async job (planning decision: not justified by a
    stub, see ADR 0020's no-infrastructure-without-a-consumer discipline).
    Swapping in a real scanner later (ClamAV, Azure Defender for Storage,
    etc.) only requires a new AntivirusScanner implementation, never a
    change to this Protocol or to documents.service's call site."""

    def scan(self, content: bytes) -> ScanResult:
        return ScanResult(clean=EICAR_SIGNATURE not in content)
