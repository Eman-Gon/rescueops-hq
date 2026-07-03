# IT Operations Severity Rubric

- **SEV-1** — Full outage, service down, or data loss. A core dependency that is
  fully unavailable and cascading into system-wide overload counts as service down,
  even when some user-facing requests still return.
- **SEV-2** — Customer-facing degradation, such as elevated errors or latency, while
  the service remains available.
- **SEV-3** — Internal-only issue with no customer impact.

Evaluate SEV-1 first, then SEV-2, then SEV-3. Choose the first definition the
incident clearly satisfies and name the matched rule in the reason.
