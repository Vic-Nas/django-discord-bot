# Testing

## Unit Tests (Automatic - GitHub Actions)

```bash
pytest tests/test_handlers.py -v
```

5 tests that run automatically on every push. Test handlers in isolation with mocked Discord objects. Very fast (~16 seconds).

**What it catches:**
- Field errors (like the `is_deleted` bug that broke member_join)
- Handler logic errors
- Database operation errors

**These would have caught the `is_deleted` issue immediately before deployment.**

---

## Integration Tests (Manual - Real Discord)

```bash
export TEST_GUILD_ID=your_test_server_id
pytest tests/test_integration.py -m integration -v
```

6 tests that connect to a real Discord server and test with actual guild objects, roles, and channels.

**Setup once:**
1. Create a separate test Discord server
2. Add your bot to it (make it Admin)
3. Set in `.env`: `TEST_GUILD_ID=your_server_id`

**What it tests:**
- Real role validation (role exists in guild)
- Real channel creation/deletion
- Real role linking 
- Handler behavior with actual Discord data
- DM vs server context
- Database changes after real operations
- Cleanup between tests

**Why this is important:**
- Tests the actual objects handlers work with
- Would have caught the `guild.roles.filter(is_deleted=False)` bug
- Can test channel operations (only possible with real guild)
- Simulates real user scenarios

---

## Running Tests Locally

### Unit tests only (no setup needed):
```bash
pip install -r requirements-dev.txt
pytest tests/test_handlers.py -v
```

### Integration tests (with real Discord):
```bash
# In terminal 1: create Discord test server and add bot

# In terminal 2: set env and run tests
export TEST_GUILD_ID=123456789  # your test server
pytest tests/test_integration.py -m integration -v

# Watch responses in Discord test server in real time
```

### Both:
```bash
pytest tests/ -v
```

---

## Pre-commit Hooks (Local Machine)

```bash
pre-commit install
```

Runs automatically before each commit. Validates syntax, imports, Django checks.

---

## GitHub Actions CI/CD

`.github/workflows/tests.yml` runs automatically on every push:
- Syntax validation
- Import checks  
- Unit tests (with pytest-django and real SQLite database)
- **Fails the build if any test fails** ← prevents broken code from reaching main

Check status in GitHub Actions tab of your repo.

---

## Test Results

**If a test fails:**
```
FAILED tests/test_integration.py::TestHandlersWithRealGuild::test_add_invite_rule_with_real_roles
AssertionError: assert rule.roles.count() > 0
```

This means the handler didn't properly link the role. Check:
1. Handler code
2. Database state
3. Discord role availability

**All 5 unit tests passing + integration tests passing = Ready to deploy.**
