#!/usr/bin/env python3
"""Read CSV file and manage users in bulk via API"""

import argparse
import csv
import sys

import requests


def main():
    """Main function to read CSV and create users via API"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-f",
        "--file",
        help=(
            "Path to the CSV file containing user data. First row is header. "
            "Columns: list_id,email,name,comment"
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
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else {}
    api_base: str = args.url + "/api/v1/lists/{list_id}/subscribers"

    with open(args.file, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            list_id = row.get("list_id")
            email = row.get("email")
            name = row.get("name")
            comment = row.get("comment")

            if args.operation == "add":
                data = {"email": email, "name": name, "comment": comment}
                response = requests.put(
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
                print(f"Unknown operation: {args.operation}")
                continue

            if response.status_code in (200, 201, 204):
                print(f"Successfully performed {args.operation} for {email} in list {list_id}")
            else:
                print(
                    f"Failed to perform {args.operation} for {email} in list {list_id}: "
                    f"{response.status_code} {response.text}"
                )
                sys.exit(1)


if __name__ == "__main__":
    main()
