"""Fase 4 — rapport per e-mail versturen. NOG NIET GEBOUWD.

Ontbreekt: SMTP-gegevens (zie CLAUDE.md §6 / .env.example).
Gebruik smtplib + email.mime zodra de gegevens bekend zijn — geen externe
mailservice aannemen.
"""


def verstuur_rapport(*args, **kwargs):
    raise NotImplementedError(
        "Fase 4 (e-mail) is nog niet geïmplementeerd — wacht op SMTP-gegevens."
    )
