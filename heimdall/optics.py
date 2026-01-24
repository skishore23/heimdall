"""
Profunctor Optics for Bidirectional Data Flow

Advanced lens system based on profunctor optics from category theory.
Provides composable, bidirectional data access patterns.

Core Concepts:
- Lens: Bidirectional accessor (get/set)
- Prism: Partial accessor (may fail)
- Traversal: Multiple target accessor
- Iso: Bidirectional isomorphism
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from .types import Ctx

# Type variables
S = TypeVar('S')  # Source type
T = TypeVar('T')  # Target type after set
A = TypeVar('A')  # Focus type
B = TypeVar('B')  # New focus type


@dataclass
class Lens(Generic[S, A]):
    """
    Lens: Bidirectional accessor

    Laws:
    1. get-put: set(s, get(s)) = s
    2. put-get: get(set(s, a)) = a
    3. put-put: set(set(s, a), b) = set(s, b)
    """
    get: Callable[[S], A]
    set: Callable[[S, A], S]

    def compose(self, other: 'Lens[A, B]') -> 'Lens[S, B]':
        """Compose two lenses"""
        def composed_get(s: S) -> B:
            a = self.get(s)
            return other.get(a)

        def composed_set(s: S, b: B) -> S:
            a = self.get(s)
            new_a = other.set(a, b)
            return self.set(s, new_a)

        return Lens(get=composed_get, set=composed_set)

    def modify(self, f: Callable[[A], A]) -> Callable[[S], S]:
        """Modify the focus using a function"""
        def modifier(s: S) -> S:
            a = self.get(s)
            new_a = f(a)
            return self.set(s, new_a)
        return modifier


@dataclass
class Prism(Generic[S, A]):
    """
    Prism: Partial accessor (may fail to focus)

    Used for sum types / optional values

    Laws:
    1. review-preview: preview(review(a)) = Just(a)
    2. preview-review: fmap(review) . preview = id
    """
    preview: Callable[[S], A | None]  # Extract if possible
    review: Callable[[A], S]  # Construct

    def compose(self, other: 'Prism[A, B]') -> 'Prism[S, B]':
        """Compose two prisms"""
        def composed_preview(s: S) -> B | None:
            maybe_a = self.preview(s)
            if maybe_a is None:
                return None
            return other.preview(maybe_a)

        def composed_review(b: B) -> S:
            a = other.review(b)
            return self.review(a)

        return Prism(preview=composed_preview, review=composed_review)


@dataclass
class Traversal(Generic[S, A]):
    """
    Traversal: Access multiple targets

    Focuses on 0 or more targets within a structure
    """
    get_all: Callable[[S], list[A]]
    set_all: Callable[[S, list[A]], S]

    def modify_all(self, f: Callable[[A], A]) -> Callable[[S], S]:
        """Modify all targets"""
        def modifier(s: S) -> S:
            targets = self.get_all(s)
            new_targets = [f(t) for t in targets]
            return self.set_all(s, new_targets)
        return modifier

    def filter(self, predicate: Callable[[A], bool]) -> 'Traversal[S, A]':
        """Filter traversal targets by predicate"""
        def filtered_get_all(s: S) -> list[A]:
            return [a for a in self.get_all(s) if predicate(a)]

        def filtered_set_all(s: S, new_values: list[A]) -> S:
            all_values = self.get_all(s)
            filtered_indices = [i for i, a in enumerate(all_values) if predicate(a)]

            if len(new_values) != len(filtered_indices):
                raise ValueError("Number of new values doesn't match filtered count")

            result = list(all_values)
            for idx, new_val in zip(filtered_indices, new_values, strict=False):
                result[idx] = new_val

            return self.set_all(s, result)

        return Traversal(get_all=filtered_get_all, set_all=filtered_set_all)


@dataclass
class Iso(Generic[S, A]):
    """
    Isomorphism: Bidirectional conversion

    Laws:
    1. from . to = id
    2. to . from = id
    """
    to: Callable[[S], A]
    from_: Callable[[A], S]

    def reverse(self) -> 'Iso[A, S]':
        """Reverse the isomorphism"""
        return Iso(to=self.from_, from_=self.to)

    def compose(self, other: 'Iso[A, B]') -> 'Iso[S, B]':
        """Compose two isomorphisms"""
        def composed_to(s: S) -> B:
            a = self.to(s)
            return other.to(a)

        def composed_from(b: B) -> S:
            a = other.from_(b)
            return self.from_(a)

        return Iso(to=composed_to, from_=composed_from)


# Common lens constructors

def attr_lens(attr_name: str) -> Lens[dict, Any]:
    """Create lens for dictionary attribute"""
    def get(d: dict) -> Any:
        return d.get(attr_name)

    def set(d: dict, value: Any) -> dict:
        new_dict = d.copy()
        new_dict[attr_name] = value
        return new_dict

    return Lens(get=get, set=set)


def index_lens(index: int) -> Lens[list, Any]:
    """Create lens for list index"""
    def get(lst: list) -> Any:
        if 0 <= index < len(lst):
            return lst[index]
        return None

    def set(lst: list, value: Any) -> list:
        new_list = lst.copy()
        if 0 <= index < len(new_list):
            new_list[index] = value
        return new_list

    return Lens(get=get, set=set)


def path_lens(path: str) -> Lens[dict, Any]:
    """Create lens for nested dictionary path"""
    keys = path.split('.')

    def get(d: dict) -> Any:
        current = d
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def set(d: dict, value: Any) -> dict:
        import copy
        new_dict = copy.deepcopy(d)
        current = new_dict

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value
        return new_dict

    return Lens(get=get, set=set)


def optional_prism(default: A) -> Prism[A | None, A]:
    """Create prism for Optional values"""
    def preview(maybe: A | None) -> A | None:
        return maybe

    def review(a: A) -> A | None:
        return a

    return Prism(preview=preview, review=review)


def list_traversal() -> Traversal[list[A], A]:
    """Create traversal for all list elements"""
    def get_all(lst: list[A]) -> list[A]:
        return list(lst)

    def set_all(lst: list[A], new_values: list[A]) -> list[A]:
        return list(new_values)

    return Traversal(get_all=get_all, set_all=set_all)


def dict_values_traversal() -> Traversal[dict, Any]:
    """Create traversal for all dictionary values"""
    def get_all(d: dict) -> list[Any]:
        return list(d.values())

    def set_all(d: dict, new_values: list[Any]) -> dict:
        keys = list(d.keys())
        if len(keys) != len(new_values):
            raise ValueError("Number of values doesn't match dict size")
        return dict(zip(keys, new_values, strict=False))

    return Traversal(get_all=get_all, set_all=set_all)


def identity_iso() -> Iso[A, A]:
    """Identity isomorphism"""
    return Iso(to=lambda x: x, from_=lambda x: x)


def json_string_iso() -> Iso[dict, str]:
    """Isomorphism between dict and JSON string"""
    import json

    def to(d: dict) -> str:
        return json.dumps(d)

    def from_(s: str) -> dict:
        return json.loads(s)

    return Iso(to=to, from_=from_)


# Guard integration

from .types import Either, Guard, Right_


def lens_guard(lens: Lens[Ctx, Any], transform: Callable[[Any], Any]) -> Guard:
    """
    Create guard that uses lens to focus and transform data

    Args:
        lens: Lens to focus on data
        transform: Transformation to apply

    Returns:
        Guard that applies transformation via lens
    """
    async def run(ctx: Ctx) -> Either:
        value = lens.get(ctx)
        new_value = transform(value)
        new_ctx = lens.set(ctx, new_value)
        return Right_(new_ctx)

    return run


def prism_guard(
    prism: Prism[Ctx, Any],
    on_match: Guard,
    on_miss: Guard | None = None
) -> Guard:
    """
    Create guard that uses prism to conditionally apply guards

    Args:
        prism: Prism to preview data
        on_match: Guard to apply if prism matches
        on_miss: Optional guard for when prism doesn't match

    Returns:
        Conditional guard based on prism
    """
    async def run(ctx: Ctx) -> Either:
        maybe_value = prism.preview(ctx)

        if maybe_value is not None:
            # Prism matched, apply on_match guard
            focused_ctx = prism.review(maybe_value)
            return await on_match(focused_ctx)

        # Prism didn't match
        if on_miss:
            return await on_miss(ctx)

        return Right_(ctx)

    return run


def traversal_guard(
    traversal: Traversal[Ctx, Any],
    element_guard: Guard
) -> Guard:
    """
    Create guard that applies element guard to all traversal targets

    Args:
        traversal: Traversal to focus on multiple targets
        element_guard: Guard to apply to each element

    Returns:
        Guard that processes all traversal targets
    """
    async def run(ctx: Ctx) -> Either:
        from .types import get_context, get_violations, is_left

        elements = traversal.get_all(ctx)
        new_elements = []
        all_violations = []

        for elem in elements:
            result = await element_guard({"output": elem})

            if is_left(result):
                all_violations.extend(get_violations(result))
            else:
                processed = get_context(result)
                new_elements.append(processed.get("output", elem))

        if all_violations:
            from .types import Left_
            return Left_(all_violations)

        new_ctx = traversal.set_all(ctx, new_elements)
        return Right_(new_ctx)

    return run

