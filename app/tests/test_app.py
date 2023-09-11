import os
from unittest.mock import patch

import freezegun

from app.models import SnookerMatch

os.environ["TWILIO_NO_SEND"] = "True"


@freezegun.freeze_time("2023-09-11")
def test_successful_request(test_client_with_mocks, mock_llm):
    """Tests that a successful request is handled correctly.

    LLM is mocked to return a mock match."""
    # Arrange
    mock_match = SnookerMatch.construct(  # skips validation
        group="1",
        player1="Huhtala Katja",
        player2="Andersson Leila",
        player1_score=2,
        player2_score=1,
        winner="Huhtala Katja",
        highest_break=45,
        break_owner="Huhtala Katja",
    )
    # Act

    # force mock_llm to return a mock match
    with patch.object(mock_llm, "run", return_value=mock_match.dict()):
        response = test_client_with_mocks.post(
            "/scores", data={"Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.", "From": "+358123456789"}
        )

    # Assert
    assert response.status_code == 201
    assert response.json() == {
        "status": "Match recorded",
        "match": {
            "date": "2023-09-11",
            "group": "1",
            "player1": "Huhtala Katja",
            "player2": "Andersson Leila",
            "player1_score": 2,
            "player2_score": 1,
            "winner": "Huhtala Katja",
            "highest_break": 45,
            "break_owner": "Huhtala Katja",
        },
    }

