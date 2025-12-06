# Sender Authorization

This document explains how CastMail2List controls who can send messages to a mailing list. The authorization logic differs between the two list modes (`broadcast` and `group`) but shares common mechanisms.

## Authorization Mechanisms

CastMail2List provides two ways to authorize senders:

1. **Allowed Senders** - A list of email addresses that are permitted to send messages
2. **Sender Authentication** - Password-based authentication via email address suffix (e.g., `list+password@example.com`)

### Email Address Normalization

- All subscriber email addresses are stored in **lowercase** in the database
- `allowed_senders` are normalized to **lowercase** when saved
- Incoming email addresses are compared **case-insensitively** (converted to lowercase for comparison)
- `sender_auth` passwords remain **case-sensitive** for security

## Broadcast Mode

In broadcast mode, the list is designed for one-to-many communication (like announcements or newsletters).

### Authorization Rules

When **either or both** `allowed_senders` or `sender_auth` are configured:
- The sender must be authorized by **at least one** of these methods
- If **neither** is configured, **any sender** can post to the list which is a risk

### Authorization Flow

1. **Check Allowed Senders**: If sender's email is in `allowed_senders` → ✅ Authorized
2. **Check Sender Authentication**: If sender provides valid password via `list+password@example.com` → ✅ Authorized
3. **Reject**: If neither succeeds → ❌ Message rejected with status `sender-not-allowed`

### Example Scenarios

**Scenario 1: Only allowed_senders configured**
```
allowed_senders: ["admin@example.com", "news@example.com"]
sender_auth: []

✅ admin@example.com can send
✅ ADMIN@Example.com can send (case-insensitive)
❌ user@example.com cannot send
```

**Scenario 2: Only sender_auth configured**
```
allowed_senders: []
sender_auth: ["secret123", "pass456"]

✅ anyone@anywhere.com sending to list+secret123@example.com can send
❌ anyone@anywhere.com sending to list@example.com without password cannot send
```

**Scenario 3: Both configured (either works)**
```
allowed_senders: ["admin@example.com"]
sender_auth: ["secret123"]

✅ admin@example.com sending to list@example.com can send
✅ user@example.com sending to list+secret123@example.com can send
❌ user@example.com sending to list@example.com cannot send
```

**Scenario 4: Neither configured**
```
allowed_senders: []
sender_auth: []

✅ Anyone can send to the list (unrestricted)
```

## Group Mode

In group mode, the list is designed for many-to-many communication (like discussion groups).

### Authorization Rules

The "Only subscribers can send" setting (`only_subscribers_send`) controls the base authorization:

When `only_subscribers_send` is **disabled** (default):
- **Any sender** can post to the list (no restrictions)

When `only_subscribers_send` is **enabled**:
- The sender must be authorized by **one** of these methods (checked in order):
  1. Is a subscriber of the list
  2. Listed in `allowed_senders`
  3. Provides valid `sender_auth` password

### Authorization Flow (when only_subscribers_send = true)

1. **Check Subscriber Status**: If sender is a subscriber → ✅ Authorized
2. **Check Allowed Senders**: If sender's email is in `allowed_senders` → ✅ Authorized (bypass subscriber check)
3. **Check Sender Authentication**: If sender provides valid password → ✅ Authorized (bypass subscriber check)
4. **Reject**: If none succeed → ❌ Message rejected with status `sender-not-allowed`

### Example Scenarios

**Scenario 1: Subscribers only (strict)**
```
only_subscribers_send: true
allowed_senders: []
sender_auth: []
subscribers: ["alice@example.com", "bob@example.com"]

✅ alice@example.com can send (is subscriber)
✅ bob@example.com can send (is subscriber)
❌ charlie@example.com cannot send (not subscriber)
```

**Scenario 2: Subscribers + bypass via allowed_senders**
```
only_subscribers_send: true
allowed_senders: ["moderator@example.com"]
sender_auth: []
subscribers: ["alice@example.com"]

✅ alice@example.com can send (is subscriber)
✅ moderator@example.com can send (in allowed_senders, bypasses subscriber check)
❌ charlie@example.com cannot send
```

**Scenario 3: Subscribers + bypass via sender_auth**
```
only_subscribers_send: true
allowed_senders: []
sender_auth: ["guest123"]
subscribers: ["alice@example.com"]

✅ alice@example.com can send (is subscriber)
✅ anyone@anywhere.com sending to list+guest123@example.com can send (has password)
❌ charlie@example.com sending to list@example.com cannot send
```

**Scenario 4: Open group (anyone can send)**
```
only_subscribers_send: false

✅ Anyone can send to the list
(allowed_senders and sender_auth are ignored in this case)
```

## Implementation Details

### Password Removal

When a sender successfully authenticates using `sender_auth`, the password suffix is automatically removed from the `To` header before the message is distributed to subscribers. This ensures subscribers don't see the authentication password.

Example:
- Sender sends to: `list+secret123@example.com`
- Subscribers receive with To: `list@example.com`

### Bounce Detection Bypass

Messages identified as bounce messages (delivery failure notifications) skip all sender authorization checks and are processed separately for bounce handling.

### Cross-Instance Duplicate Detection

Messages that contain the `X-CastMail2List-Domain` header matching this instance's domain are rejected as duplicates to prevent mail loops.

## Security Recommendations

### Broadcast Mode
- **Always configure** at least `allowed_senders` or `sender_auth` for broadcast lists
- Without either, anyone can send announcements on your behalf
- Use `allowed_senders` for a small number of known senders
- Use `sender_auth` for temporary or rotating authorized senders

### Group Mode
- Enable `only_subscribers_send` for private discussion groups
- Use `allowed_senders` to grant moderator privileges (can send without subscribing)
- Use `sender_auth` for guest posting with a temporary password
- For public discussion, leave `only_subscribers_send` disabled

## Status Codes

When authorization fails, the message is marked with one of these status codes:

- `sender-not-allowed` - Sender failed all authorization checks
- `sender-auth-failed` - *(legacy, now unified with sender-not-allowed)*

Messages with these statuses are moved to the `IMAP_FOLDER_DENIED` folder.
