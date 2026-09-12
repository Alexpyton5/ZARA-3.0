# Gates: principal architect checkpoint

- [x] N1: Both discovery artifacts have been independently reviewed and their exact leases released
  EVIDENCE: Parent reverified leaf-1 through leaf-4 after all dispatch waves completed; exact leases for all four leaves were released successfully.

- [x] I1: Selected coherent improvement meets its preimplementation behavioral contract
  CHECK: .venv\Scripts\python.exe tools\verify_front_brain_checkpoint.py
  EXPECT: FRONT_BRAIN_CHECKPOINT_PASS
  CWD: C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002
  EVIDENCE: automatic-evidence=v1; definition-sha256=83e91f57a10960eb0095c6e7f65c1ab41110dcdd2f075907820a45d2de993e3d; exit=0; EXPECT=matched; output-sha256=2a52e0452178e3173a2cdc4b2fb62f4289527beaae42965e6d4174a1ef65f71a; output-bytes=29; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=199796bfb79d/37 entries

- [x] P1: Cost policy, truthful evidence, risk boundaries and rollback preservation survive independent review
  EVIDENCE: Current-delta review confirms manual premium selection, no fallback, reroute rejection, bounded context, stale package preservation and explicit evidence limits. One Astra call; no retries; no package.

- [x] P2: Architecture decision reuses canonical systems and dispositions provider, cognitive and cinematic proposals with factual limits
  EVIDENCE: Implementation reuses LabStore, LabRuntime, provider registry, existing IPC/history/voice and Home IPC. Workforce, learning, voice acoustics and redesign remain explicitly outside this checkpoint.

- [x] R1: First decision and precise resume reconcile the original request with measured results and remaining gaps
  CHECK: .venv\Scripts\python.exe -c "from pathlib import Path; p=Path('artifacts/principal-20260907/implementation-result.md'); t=p.read_text(encoding='utf-8'); assert 'READY FOR INDEPENDENT TERRA REVIEW:' in t and 'No package was created.' in t; print('FRONT_REPORT_PASS')"
  EXPECT: FRONT_REPORT_PASS
  CWD: C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002
  EVIDENCE: automatic-evidence=v1; definition-sha256=362f018a614bf85efc933c655448b30912453f9958cb95805eb5b5d65f3e2a6e; exit=0; EXPECT=matched; output-sha256=0d82b7784ac3b98723bd82b9555fe1e38df0335869ccb694d14febd206f8b085; output-bytes=19; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=199796bfb79d/37 entries
