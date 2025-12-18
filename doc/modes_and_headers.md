<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# Mailing-list Modes and Message Headers

This document summarizes how the two mailing-list modes (`broadcast` and `group`) and
related list settings affect outbound messages produced by CastMail2List. It focuses on
headers and per-recipient behavior so you can quickly see where the modes differ and
where they behave the same.

## Overview

- Modes: `broadcast`, `group`.
- Many headers are set the same regardless of mode (threading, list metadata, X-Mailer,
  etc.). The crucial differences are in `From`, `Reply-To`, `X-MailFrom`, and how the
  `To` header is constructed for each recipient.

## Headers common to both modes

- `X-Mailer`: `CastMail2List` (always present).
- `X-CastMail2List-Domain`: application `DOMAIN` config (always present).
- `List-Id`: set to `<list.address.replace('@', '.')>`.
- `Precedence`: `list`.
- `Sender`: the list address (`ml.address`).
- `Message-ID`: a new message-id generated for the outgoing message.
- `Original-Message-ID`: the incoming message's Message-ID (if any).
- `Date`: incoming `date_str` or current date/time.
- Threading headers: `In-Reply-To`, `References` are preserved/constructed from the
  incoming message to keep threads intact.
- `X-Recipient`: set per-recipient at send time to ease debugging.
- SMTP envelope-from: constructed using `create_bounce_address(ml_address, recipient)`
  (this is the envelope/bounce address used for SMTP delivery in both modes).

## Sanity checks

- If `msg.from_values` is missing, the code logs an error and cannot prepare the proper `From` header (sending is not performed).

## Broadcast mode (ml.mode == "broadcast")

- From header:
  - `From` is the list's configured `from_addr` if set (allows a custom sender address).
  - If no `from_addr` is configured, uses `"Sender Name via List Name <list@address>"`
    format (same as group mode).
- Reply-To:
  - If `from_addr` is set: No `Reply-To` header (replies go to the custom From address).
  - If no `from_addr`: `Reply-To` is set to the original sender's email address to allow
    direct replies.
- X-MailFrom:
  - If `from_addr` is set: Not set.
  - If no `from_addr`: Set to the original sender's email address (for debugging/tracking).
- To/Cc handling:
  - The list address is removed from `To` and `Cc` when composing the outgoing
    message (to avoid confusion).
  - When sending to each subscriber, the recipient is appended to the per-recipient
    `msg.to` so the `To:` header includes the recipient (and any preserved original
    To addresses).
- Avoid-duplicates:
  - If `ml.avoid_duplicates` is true, subscribers already present in original `To`/`Cc`
    are skipped (no send).

## Group mode (ml.mode == "group")

- From header:
  - `From` is set to `"Sender Name via List Name <list@address>"` (built from the
    original sender and the list name). This exposes the original sender while still
    showing the list context.
- Reply-To:
  - By default `Reply-To` is the list name and address (`ml.display <ml.address>`).
  - If the original sender is not a subscriber, the header becomes
    `Sender <original-sender>, List <list-address>"` so replies go to both the sender and the list.
  - If the original sender is a subscriber, `Reply-To` is just the list name and address.
- X-MailFrom:
  - `X-MailFrom` is set to the original sender's email address (helps debugging).
- To/Cc handling:
  - The original To/Cc are preserved (no automatic per-recipient append in the
    same way broadcast does). Replies are routed to the list by `Reply-To`.
- Avoid-duplicates:
  - The same `ml.avoid_duplicates` behaviour applies.

## Per-recipient behavior and sending

- A `Mail` object is composed from the incoming message and list metadata. Before
  sending to each subscriber the code `deepcopy`s this `Mail` object so per-recipient
  header mutations (such as adding the recipient to `To` in broadcast mode) do not
  leak to other recipients.
- For each subscriber, `send_email_to_recipient()` sets `To` and `X-Recipient` and
  returns the sent bytes. Successfully sent messages are appended to the IMAP
  `IMAP_FOLDER_SENT` folder via `mailbox.append()`.

## Envelope vs Header From

- The SMTP envelope-from (used for bounces) is NOT the same as the `From:` header
  shown to users. The envelope-from is generated per-recipient using
  `create_bounce_address(ml_address, recipient)` in both modes. This centralizes
  bounce handling at the list and keeps message `From:` semantics independent.

## Edge cases and notes

- If `msg.from_values` is absent in `group` mode the message cannot be formed with
  the standard "Sender via List" `From` and is logged as an error — group mode relies
  on a valid original From.
- Bounce-detection is performed earlier when messages are fetched from IMAP. If a
  message is classified as a bounce it is stored with status `bounce-msg` and moved
  to the `IMAP_FOLDER_BOUNCES` folder and is not sent to subscribers.

## Quick reference table

| Header / Behavior                        |                                broadcast                                |                              group                               |
| :--------------------------------------- | :---------------------------------------------------------------------: | :--------------------------------------------------------------: |
| From                                     | `ml.from_addr` (if set) or `"Sender Name via List Name <list@address>"` |          `"Sender Name via List Name <list@address>"`            |
| Reply-To                                 |           original sender email, or none if `from_addr` set             | `ml.address`, or `"sender, ml.address"` if sender not subscriber |
| X-MailFrom                               |          (not set if `from_addr` set) or original sender email          |                      original sender email                       |
| To header mutation                       |                    recipient appended per-recipient                     |                      original To preserved                       |
| Avoid duplicates (`ml.avoid_duplicates`) |                                 applies                                 |                             applies                              |
| SMTP envelope-from                       |                      per-recipient bounce address                       |                  per-recipient bounce address                    |
