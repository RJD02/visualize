from dataclasses import dataclass
from typing import List, Protocol


class Repository(Protocol):
    def save(self, entity):
        ...


@dataclass
class User:
    id: int
    email: str


@dataclass
class Order:
    id: int
    user_id: int
    items: List[str]


class UserRepository:
    def save(self, entity: User):
        pass


class OrderRepository:
    def save(self, entity: Order):
        pass


class EmailService:
    def send_receipt(self, email: str, order_id: int):
        pass


class PaymentService:
    def charge(self, user_id: int, amount: float) -> bool:
        return True


class OrderService:
    def __init__(self, user_repo: UserRepository, order_repo: OrderRepository, payment: PaymentService, email: EmailService):
        self.user_repo = user_repo
        self.order_repo = order_repo
        self.payment = payment
        self.email = email

    def place_order(self, user: User, items: List[str], amount: float) -> Order:
        if not self.payment.charge(user.id, amount):
            raise ValueError("Payment failed")
        order = Order(id=1, user_id=user.id, items=items)
        self.order_repo.save(order)
        self.email.send_receipt(user.email, order.id)
        return order


class OrderController:
    def __init__(self, service: OrderService):
        self.service = service

    def create_order(self, user_id: int, items: List[str], amount: float):
        user = User(id=user_id, email="u@example.com")
        return self.service.place_order(user, items, amount)
