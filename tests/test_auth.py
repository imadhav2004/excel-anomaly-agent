from datetime import timedelta

import pytest
from sqlalchemy import select, text

from anomaly_agent import auth
from anomaly_agent.auth import AuthError, MAX_ATTEMPTS, change_password, delete_account, login, register_user
from anomaly_agent.db.database import session_scope
from anomaly_agent.db.models import User, utcnow

GOOD = "Sup3rSecret1"


def make(email="asha@example.com", name="Asha", password=GOOD):
    with session_scope() as session:
        return register_user(session, name, email, password)


def test_register_stores_a_hash_never_the_password():
    user = make()
    assert user == {"id": user["id"], "name": "Asha", "email": "asha@example.com"}
    with session_scope() as session:
        stored = session.scalar(select(User)).password_hash
        raw = session.execute(text("select password_hash from users")).scalar()
    assert stored == raw
    assert GOOD not in stored
    assert stored.startswith("$2")  # a bcrypt hash


def test_two_users_with_the_same_password_get_different_hashes():
    make("a@example.com")
    make("b@example.com")
    with session_scope() as session:
        hashes = {u.password_hash for u in session.scalars(select(User))}
    assert len(hashes) == 2  # every hash has its own random salt


def test_email_is_cleaned_and_unique_ignoring_case():
    make(" Asha@Example.COM ")
    with pytest.raises(AuthError, match="already exists"):
        make("asha@example.com", name="Someone Else")
    with session_scope() as session:
        assert session.scalar(select(User.email)) == "asha@example.com"


@pytest.mark.parametrize("email", ["", "plain", "a@b", "a b@example.com", "@example.com", "x" * 250 + "@example.com"])
def test_bad_emails_are_refused(email):
    with pytest.raises(AuthError, match="valid email"):
        make(email)


@pytest.mark.parametrize(
    "password, message",
    [
        ("short1", "at least 8"),
        ("onlyletters", "letter and one number"),
        ("12345678", "letter and one number"),
        ("a1" * 40, "too long"),
        ("asha@example.com", "letter and one number"),
    ],
)
def test_weak_passwords_are_refused(password, message):
    with pytest.raises(AuthError, match=message):
        make(password=password)


def test_a_password_equal_to_the_email_is_refused():
    with pytest.raises(AuthError, match="same as the email"):
        make("asha1234@example.com", password="Asha1234@Example.com")


def test_name_is_required():
    with pytest.raises(AuthError, match="name"):
        make(name=" ")


def test_login_works_with_any_capitalisation_of_the_email():
    make()
    with session_scope() as session:
        assert login(session, "  ASHA@example.com ", GOOD)["name"] == "Asha"


def test_wrong_password_and_unknown_email_give_the_same_message():
    make()
    with session_scope() as session:
        with pytest.raises(AuthError) as wrong:
            login(session, "asha@example.com", "Wrong-Pass1")
        with pytest.raises(AuthError) as unknown:
            login(session, "nobody@example.com", "Wrong-Pass1")
    assert str(wrong.value) == str(unknown.value) == auth.WRONG_LOGIN


def test_account_locks_after_too_many_wrong_passwords_then_opens_again():
    make()
    now = utcnow()
    for _ in range(MAX_ATTEMPTS):
        with session_scope() as session:
            with pytest.raises(AuthError, match="Wrong email"):
                login(session, "asha@example.com", "Wrong-Pass1", now=now)
    with session_scope() as session:  # even the RIGHT password is refused while locked
        with pytest.raises(AuthError, match="Too many wrong attempts"):
            login(session, "asha@example.com", GOOD, now=now + timedelta(minutes=1))
    with session_scope() as session:  # after the lock time it works again
        assert login(session, "asha@example.com", GOOD, now=now + timedelta(minutes=auth.LOCK_MINUTES + 1))


def test_a_good_login_resets_the_wrong_attempt_counter():
    make()
    for _ in range(MAX_ATTEMPTS - 1):
        with session_scope() as session:
            with pytest.raises(AuthError):
                login(session, "asha@example.com", "Wrong-Pass1")
    with session_scope() as session:
        login(session, "asha@example.com", GOOD)
    with session_scope() as session:
        assert session.scalar(select(User.failed_attempts)) == 0
        assert session.scalar(select(User.last_login)) is not None
    for _ in range(MAX_ATTEMPTS - 1):  # four more mistakes do not lock, because the counter restarted
        with session_scope() as session:
            with pytest.raises(AuthError, match="Wrong email"):
                login(session, "asha@example.com", "Wrong-Pass1")


def test_sql_text_in_the_email_is_just_text():
    make()
    attack = "x@example.com' OR '1'='1"
    with session_scope() as session:
        with pytest.raises(AuthError):
            login(session, attack, "anything1")
        with pytest.raises(AuthError):
            login(session, "' OR 1=1 --", "anything1")
    with session_scope() as session:
        assert session.scalar(select(User.email)) == "asha@example.com"  # the table is intact


def test_change_password():
    user = make()
    with session_scope() as session:
        with pytest.raises(AuthError, match="current password is wrong"):
            change_password(session, user["id"], "Wrong-Pass1", "N3wSecretPass")
        with pytest.raises(AuthError, match="at least 8"):
            change_password(session, user["id"], GOOD, "x1")
        change_password(session, user["id"], GOOD, "N3wSecretPass")
    with session_scope() as session:
        assert login(session, "asha@example.com", "N3wSecretPass")
        with pytest.raises(AuthError):
            login(session, "asha@example.com", GOOD)


def test_delete_account_needs_the_password_and_removes_saved_analyses():
    from anomaly_agent.db.analyses import list_analyses, save_analysis

    user = make()
    with session_scope() as session:
        save_analysis(session, user["id"], "f.xlsx", "Oct 2026", 12, [])
        with pytest.raises(AuthError, match="not deleted"):
            delete_account(session, user["id"], "Wrong-Pass1")
    with session_scope() as session:
        delete_account(session, user["id"], GOOD)
    with session_scope() as session:
        assert session.scalar(select(User)) is None
        assert list_analyses(session, user["id"]) == []


def test_a_broken_stored_hash_means_no_login_instead_of_a_crash():
    assert auth.verify_password("whatever1", "not-a-hash") is False
    assert auth.verify_password("whatever1", "") is False
