import logging

import click
from tabulate import tabulate

from .sheets import SnookerSheet


def print_players(players):
    """Display current players and round"""
    player_table = [[player.name, player.group] for player in players]
    print(tabulate(player_table, headers=["PLAYER", "GROUP"], tablefmt="simple"))


@click.group()
@click.option("--sheet-id", "-s", type=str, help="Google Sheet ID")
@click.pass_context
def cli(ctx, sheet_id):
    if not sheet_id:
        sheet_id = input("Please enter the sheet ID: ")
    ctx.ensure_object(dict)
    ctx.obj["sheet_id"] = sheet_id


@cli.command()
@click.pass_context
def players(ctx):
    """List current players"""
    sheet_id = ctx.obj["sheet_id"]
    sheet = SnookerSheet(sheet_id)
    current_round = sheet.current_round
    players = sheet.current_players
    print(f"Current Round: {current_round}")
    print_players(players)


@cli.command()
@click.pass_context
def make_fixtures(ctx):
    """Make match fixtures for the current round"""
    sheet_id = ctx.obj["sheet_id"]
    sheet = SnookerSheet(sheet_id)
    current_round = sheet.current_round

    print_players(sheet.current_players)

    confirmation = input(f"Are you sure you want to create match fixtures to sheet {sheet_id}? (yes/no): ")
    if confirmation.lower() == "yes":
        sheet.make_fixtures(current_round)
        logging.info("Fixtures added for round %s", current_round)
    else:
        logging.info("Operation cancelled by user.")


if __name__ == "__main__":
    cli(obj={})
