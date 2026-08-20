import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from app.models import Entry, Match, MatchResult, Round

_OUTCOME_RESULT = {
    "1": MatchResult.ENTRY1_WIN,
    "2": MatchResult.ENTRY2_WIN,
    "3": MatchResult.TIE,
}


def load_tom_pod(
    xml_path: Path, pod_category: str
) -> tuple[list[Entry], list[Round], dict[str, uuid.UUID]]:
    """Parse a TOM export's <pod category=pod_category> into Entry/Round
    fixtures for PokemonTiebreak/SwissFormat.

    Returns (entries, rounds, userid_to_entry_id) so callers can translate
    TOM userids from <standings> into the same Entry.id values used here.
    """
    root = ET.parse(xml_path).getroot()
    id_map: dict[str, uuid.UUID] = {}

    def entry_id_for(userid: str) -> uuid.UUID:
        return id_map.setdefault(userid, uuid.uuid4())

    dropped_at_round: dict[str, int] = {}
    for player_el in root.find("players"):
        userid = player_el.get("userid")
        dropped_round_el = player_el.find("dropped/round")
        if dropped_round_el is not None:
            dropped_at_round[userid] = int(dropped_round_el.text)

    pod_el = next(pod for pod in root.find("pods") if pod.get("category") == pod_category)
    pod_id = uuid.uuid4()

    entries: list[Entry] = []
    for player_el in pod_el.find("subgroups/subgroup/players"):
        userid = player_el.get("userid")
        entries.append(
            Entry(
                id=entry_id_for(userid),
                pod_id=pod_id,
                player_uuid=uuid.uuid4(),
                source_system="tom-import",
                metadata_={},
                dropped_at_round=dropped_at_round.get(userid),
            )
        )

    rounds: list[Round] = []
    for round_el in pod_el.find("rounds"):
        matches: list[Match] = []
        for match_el in round_el.find("matches"):
            outcome = match_el.get("outcome")
            if outcome == "5":
                bye_userid = match_el.find("player").get("userid")
                matches.append(
                    Match(
                        id=uuid.uuid4(),
                        round_id=uuid.uuid4(),
                        entry1_id=entry_id_for(bye_userid),
                        entry2_id=None,
                        result=MatchResult.UNREPORTED,
                    )
                )
                continue

            player1_userid = match_el.find("player1").get("userid")
            player2_userid = match_el.find("player2").get("userid")
            matches.append(
                Match(
                    id=uuid.uuid4(),
                    round_id=uuid.uuid4(),
                    entry1_id=entry_id_for(player1_userid),
                    entry2_id=entry_id_for(player2_userid),
                    result=_OUTCOME_RESULT[outcome],
                )
            )

        round_ = Round(id=uuid.uuid4(), pod_id=pod_id, number=int(round_el.get("number")))
        round_.matches = matches
        rounds.append(round_)

    return entries, rounds, id_map


def load_tom_standings(
    xml_path: Path, standings_category: str, id_map: dict[str, uuid.UUID]
) -> list[uuid.UUID]:
    """Parse a TOM export's finished <standings><pod category=...> block
    into an Entry.id list ordered by place ascending, translated through
    id_map (from load_tom_pod) so it's directly comparable to a
    SwissFormat.compute_standings() result's entry_id order."""
    root = ET.parse(xml_path).getroot()
    standings_pod = next(
        pod
        for pod in root.find("standings")
        if pod.get("category") == standings_category and pod.get("type") == "finished"
    )
    placed = sorted(standings_pod.findall("player"), key=lambda el: int(el.get("place")))
    return [id_map[player_el.get("id")] for player_el in placed]
