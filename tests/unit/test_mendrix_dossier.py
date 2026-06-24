"""Unit tests voor mendrix_dossier.py — upload_naar_dossier."""

import pytest

from lokalist_weekrapportage.mendrix_dossier import upload_naar_dossier


def test_upload_naar_dossier_gooit_not_implemented():
    with pytest.raises(NotImplementedError):
        upload_naar_dossier()
