"""Stock Type business rules.

Ports StockTypeController (store/update/destroy) + StoreStockTypeRequest
validation + StockType model. UI-agnostic: raises ValidationError /
DeleteBlocked / ConfirmRequired which the view turns into dialogs.

Validation (StoreStockTypeRequest):
  * code: required, max 10, unique; uppercased+trimmed (prepareForValidation).
  * name: required, max 30; trimmed.
  * def / compare: nullable boolean -> stored 1/0.

Delete decision tree (StockTypeController::destroy):
  * usage.total == 0            -> delete.
  * total>0 and total==itemsonly-> ConfirmRequired (deletable with items via force).
  * total>0 and total!=itemsonly-> DeleteBlocked (used by transactions; cannot delete).
  * force                       -> deleteWithItems regardless.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core.audit import log_delpart
from ...core.auth import AppSession
from .repo import StockTypeRepo


class ValidationError(Exception):
    pass


class DeleteBlocked(Exception):
    def __init__(self, message: str, usage: dict):
        super().__init__(message)
        self.usage = usage


class ConfirmRequired(Exception):
    def __init__(self, message: str, usage: dict):
        super().__init__(message)
        self.usage = usage


@dataclass
class StockTypeForm:
    code: str
    name: str
    def_: bool = False
    compare: bool = False


class StockTypeService:
    def __init__(self, repo: StockTypeRepo, session: AppSession | None = None):
        self.repo = repo
        self.session = session

    def list(self) -> list[dict]:
        return self.repo.list()

    def get(self, code: str) -> dict | None:
        return self.repo.get_by_code(code)

    def get_default(self) -> dict | None:
        return self.repo.get_default()

    # -- validation ---------------------------------------------------------
    @staticmethod
    def _normalize(form: StockTypeForm) -> StockTypeForm:
        return StockTypeForm(
            code=(form.code or "").strip().upper(),
            name=(form.name or "").strip(),
            def_=bool(form.def_),
            compare=bool(form.compare),
        )

    def _validate(self, form: StockTypeForm, *, creating: bool) -> None:
        if form.code == "":
            raise ValidationError("Stock type code is required")
        if len(form.code) > 10:
            raise ValidationError("Code cannot exceed 10 characters")
        if form.name == "":
            raise ValidationError("Stock type name is required")
        if len(form.name) > 30:
            raise ValidationError("Name cannot exceed 30 characters")
        if creating and self.repo.code_exists(form.code):
            raise ValidationError("This code already exists")

    # -- commands -----------------------------------------------------------
    def create(self, form: StockTypeForm) -> dict:
        form = self._normalize(form)
        self._validate(form, creating=True)
        self.repo.create(form.code, form.name, int(form.def_), int(form.compare), form.def_)
        log_delpart(self.repo.db, self.session, f"Stock Type({form.code}) Added", utype="A", ttype="R")
        return self.repo.get_by_code(form.code) or {}

    def update(self, code: str, form: StockTypeForm) -> dict:
        code = (code or "").strip().upper()
        form = self._normalize(StockTypeForm(code=code, name=form.name, def_=form.def_, compare=form.compare))
        if not self.repo.code_exists(code):
            raise ValidationError("Stock type not found")
        self._validate(form, creating=False)
        self.repo.save(code, form.name, int(form.def_), int(form.compare), form.def_)
        log_delpart(self.repo.db, self.session, f"Stock Type({code}) Updated", utype="E", ttype="R")
        return self.repo.get_by_code(code) or {}

    def delete(self, code: str, *, force: bool = False) -> None:
        code = (code or "").strip().upper()
        if not self.repo.code_exists(code):
            raise ValidationError("Stock type not found")

        usage = self.repo.usage(code)
        if usage["total"] > 0 and not force:
            if usage["total"] == usage["itemsonly"]:
                raise ConfirmRequired(
                    "Items exist with this stock type.\nDo you want to delete this code?", usage
                )
            raise DeleteBlocked(
                "Items exist with this entry.\nYou can't delete this code.", usage
            )

        self.repo.delete_with_items(code)
        log_delpart(self.repo.db, self.session, f"Stock Type({code}) Deleted", utype="D", ttype="R")
