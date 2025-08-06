from src.utils import singleton


class TestSingleton:
    """Tests for singleton decorator."""

    def test_same_instance(self) -> None:

        @singleton
        class TestClass:
            def __init__(self, value: str = "default") -> None:
                self.value = value

        instance1 = TestClass("first")
        instance2 = TestClass("second")
        instance3 = TestClass()

        # Check that this is the same object
        assert instance1 is instance2 is instance3
        # And it has the values from the first initialization
        assert instance1.value == "first"
        assert instance2.value == "first"
        assert instance3.value == "first"

    def test_state_persistence(self) -> None:

        @singleton
        class TestClass:
            def __init__(self, value: str = "default") -> None:
                self.value = value
                self.modified = False

        instance1 = TestClass()
        instance1.value = "modified"
        instance1.modified = True

        # Create a new instance and check that the state is preserved
        instance2 = TestClass("ignored value")
        assert instance2.value == "modified"
        assert instance2.modified is True

        instance2.value = ""

    def test_multiple_singleton_classes(self) -> None:
        @singleton
        class TestClass:
            def __init__(self, value: str) -> None:
                self.value = value

        @singleton
        class AnotherTestClass:
            def __init__(self, value: int = 0) -> None:
                self.value = value

        # Create instances of different classes
        test1 = TestClass("test")
        test2 = TestClass("ignored")
        another1 = AnotherTestClass(42)
        another2 = AnotherTestClass(24)

        # Check that instances of the same class are the same
        assert test1 is test2
        assert another1 is another2

        # But instances of different classes are different
        assert test1 is not another1  # type: ignore

        # And states are not shared
        assert test1.value == "test"
        assert another1.value == 42
