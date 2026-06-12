from movie_bot.database import MovieRepository


def test_movie_lifecycle(tmp_path):
    repository = MovieRepository(f"sqlite:///{tmp_path / 'movies.db'}")
    repository.initialize()

    repository.upsert("abc", 42, "Example")
    movie = repository.get("abc")
    assert movie is not None
    assert movie.message_id == 42
    assert movie.title == "Example"
    assert repository.count() == 1

    repository.record_request("abc")
    assert repository.total_requests() == 1

    repository.upsert("abc", 99, "Updated")
    assert repository.get("abc").message_id == 99
    assert repository.count() == 1

    assert repository.delete("abc") is True
    assert repository.get("abc") is None
    assert repository.delete("abc") is False
    repository.close()
