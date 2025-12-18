#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Read CSV file and manage users in bulk via API"""

# pylint: disable=invalid-name

import argparse
import csv
import json
import logging
import sys

import requests


def configure_logger(verbose: bool = False) -> logging.Logger:
    """Set logging options"""
    log = logging.getLogger()
    logging.basicConfig(
        encoding="utf-8",
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if verbose:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    return log


def load_users_from_file(
    file_path: str, override_list_id: str = "", ignore_errors: bool = False
) -> dict[str, dict]:
    """Load users from a CSV or JSON file"""
    with open(file_path, newline="", encoding="utf-8") as inputfile:
        # JSON format
        if file_path.lower().endswith(".json"):
            data: dict[str, dict] = json.load(inputfile)
            # If list_id argument is provided, set it for all entries
            if override_list_id:
                for _, info in data.items():
                    info["list_id"] = override_list_id
            return data

        # CSV format
        if file_path.lower().endswith(".csv"):
            data = {}
            reader = csv.DictReader(inputfile)
            for row in reader:
                list_id = row.get("list_id")
                # Get list ID either from file or argument
                if list_id is None:
                    if override_list_id is None:
                        logging.error(
                            "Line %s: list_id must be provided in the file or as an argument.",
                            reader.line_num,
                        )
                        if not ignore_errors:
                            sys.exit(1)
                    list_id = override_list_id
                email = row.get("email", "")
                if not email:
                    logging.error("Line %s: email is required for each user.", reader.line_num)
                    if not ignore_errors:
                        sys.exit(1)
                name = row.get("name", "")
                comment = row.get("comment", "")
                data[email] = {
                    "list_id": list_id,
                    "name": name,
                    "email": email,
                    "comment": comment,
                }
            return data

        logging.critical("Unsupported file format. Please use CSV or JSON.")
        sys.exit(1)


def main():
    """Main function to read data files and create users via API"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-f",
        "--file",
        help=(
            "Path to the CSV or JSON file containing user data. In CSV, the first row is header "
            "([list_id],email,name,comment). In JSON, the format is a list of objects with keys: "
            "[list_id], email, name, comment."
        ),
        required=True,
    )
    parser.add_argument("-u", "--url", help="Base URL of the application", required=True)
    parser.add_argument("-a", "--api-key", help="API key for authentication", required=True)
    parser.add_argument(
        "-o",
        "--operation",
        choices=["add", "delete", "update"],
        help="Operation to perform",
        required=True,
    )
    parser.add_argument(
        "-l",
        "--list-id",
        help="ID of the list to manage users in, if this field isn't defined in the input file",
        type=str,
        required=False,
    )
    parser.add_argument("-i", "--ignore-errors", action="store_true", help="Continue on errors")
    args = parser.parse_args()

    # Configure logger
    configure_logger(verbose=False)

    # Sanity check for operation
    if args.operation not in ("add", "delete", "update"):
        logging.critical("Unknown operation: %s", args.operation)
        sys.exit(1)

    # Prepare headers for API requests
    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}

    # Load users from file
    users = load_users_from_file(args.file, args.list_id)

    for _, info in users.items():
        list_id = info.get("list_id")
        name = info.get("name", "")
        comment = info.get("comment", "")
        email = info.get("email")

        # Sanity checks
        if not list_id or not email:
            logging.error("User entry missing required fields (list_id and/or email): %s", info)
            continue

        # Prepare API endpoint
        api_base: str = args.url + "/api/v1/lists/{list_id}/subscribers"

        if args.operation == "add":
            data = {"email": email, "name": name, "comment": comment}
            response = requests.post(
                api_base.format(list_id=list_id),
                json=data,
                headers=headers,
                timeout=10,
            )
        elif args.operation == "delete":
            response = requests.delete(
                api_base.format(list_id=list_id) + f"/{email}",
                headers=headers,
                timeout=10,
            )
        elif args.operation == "update":
            data = {"name": name, "comment": comment}
            response = requests.patch(
                api_base.format(list_id=list_id) + f"/{email}",
                json=data,
                headers=headers,
                timeout=10,
            )
        else:
            logging.critical("Unsupported operation: %s", args.operation)
            sys.exit(1)

        if response.status_code in (200, 201, 204):
            logging.info(
                "Successfully performed %s for %s in list %s: %s\n%s",
                args.operation,
                email,
                list_id,
                response.status_code,
                response.text,
            )
        else:
            logging.error(
                "Failed to perform %s for %s in list %s: %s\n%s",
                args.operation,
                email,
                list_id,
                response.status_code,
                response.text,
            )
            if not args.ignore_errors:
                sys.exit(1)


if __name__ == "__main__":
    main()
