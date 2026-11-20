from where_to_go.card_photos import CardPhotos, PostPictures


def test_a_post_of_this_event_alone_gives_all_its_pictures():
    assert CardPhotos.pick("a.jpg", [PostPictures(["a.jpg", "b.jpg", "c.jpg"], 0, shared=False)]) == ["a.jpg", "b.jpg", "c.jpg"]


def test_a_digest_gives_only_the_picture_of_this_event():
    digest = PostPictures(["x.jpg", "y.jpg", "z.jpg"], 1, shared=True)
    assert CardPhotos.pick("a.jpg", [PostPictures(["a.jpg"], 0, shared=False), digest]) == ["a.jpg", "y.jpg"]


def test_a_digest_without_a_picture_of_this_event_gives_none():
    assert CardPhotos.pick(None, [PostPictures(["x.jpg", "y.jpg"], None, shared=True)]) == []


def test_frames_of_one_video_give_the_main_frame_only():
    frames = [f"v-f{i}.jpg" for i in range(6)]
    assert CardPhotos.pick("v-f4.jpg", [PostPictures(["p.jpg", *frames], 5, shared=False)]) == ["v-f4.jpg", "p.jpg"]


def test_frames_of_another_video_give_its_first_frame():
    frames = [f"w-f{i}.jpg" for i in range(3)]
    assert CardPhotos.pick("a.jpg", [PostPictures(["a.jpg", *frames], 0, shared=False)]) == ["a.jpg", "w-f0.jpg"]


def test_the_main_photo_comes_first_without_repeats():
    posts = [PostPictures(["b.jpg"], 0, shared=False), PostPictures(["a.jpg", "b.jpg"], 0, shared=False)]
    assert CardPhotos.pick("a.jpg", posts) == ["a.jpg", "b.jpg"]


def test_no_pictures_give_an_empty_list():
    assert CardPhotos.pick(None, [PostPictures([], None, shared=False)]) == []
