import ast
import operator
import math
from typing import Any

import core

# This one is completely written by AI. Sorry, but i hate math!
class SafeCalculator:
    """
    A safe calculator that evaluates mathematical expressions using AST.

    It prevents code execution by strictly validating the expression tree
    and only allowing specific mathematical operations.
    """

    def __init__(self):
        # Mapping of allowed binary operators
        self._binary_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            #ast.FloorDiv: operator.floordiv,
            #ast.Mod: operator.mod,
            #ast.Pow: operator.pow,
        }

        # Mapping of allowed unary operators
        self._unary_operators = {
            ast.UAdd: operator.pos,
            ast.USub: operator.neg,
        }

    def evaluate(self, expression: str) -> float:
        """
        Safely evaluates a mathematical expression string.

        Args:
            expression: The mathematical expression to evaluate (e.g., "2 + 2 * 3").

        Returns:
            The result of the calculation as a float (or int).

        Raises:
            ValueError: If the expression contains forbidden syntax or is invalid.
            ZeroDivisionError: If the expression attempts to divide by zero.
        """
        if not expression or not expression.strip():
            raise ValueError("Expression cannot be empty")

        # block characters not in the whitelist, just in case
        allowed = set('0123456789+-*/(). ')
        if not all(c in allowed for c in expression):
            raise ValueError("Invalid characters in expression")

        # block expressions that are too long
        if len(expression) > 100:
            raise ValueError("Expression is too long (max 100 characters)")

        try:
            # Parse the expression into an Abstract Syntax Tree (AST)
            tree = ast.parse(expression, mode='eval')
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {e}") from e

        # Recursively visit nodes to compute the result
        result = self._visit(tree.body)

        # Ensure the result is a number
        if not isinstance(result, (int, float)):
            raise ValueError("Expression did not evaluate to a number")

        return result

    def _visit(self, node: ast.AST) -> Any:
        """Recursively visit nodes in the AST."""

        # Handle literal numbers (e.g., 5, 3.14)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Invalid constant type: {type(node.value)}")

        # Handle binary operations (e.g., 2 + 3)
        if isinstance(node, ast.BinOp):
            left = self._visit(node.left)
            right = self._visit(node.right)

            op_type = type(node.op)
            if op_type in self._binary_operators:
                op_func = self._binary_operators[op_type]
                try:
                    return op_func(left, right)
                except ZeroDivisionError:
                    raise ZeroDivisionError("Division by zero in expression")

            raise ValueError(f"Binary operator {op_type.__name__} not allowed")

        # Handle unary operations (e.g., -5)
        if isinstance(node, ast.UnaryOp):
            operand = self._visit(node.operand)

            op_type = type(node.op)
            if op_type in self._unary_operators:
                op_func = self._unary_operators[op_type]
                return op_func(operand)

            raise ValueError(f"Unary operator {op_type.__name__} not allowed")

        # Handle grouping/parentheses (usually handled by tree structure, 
        # but strictly we only allow expressions we explicitly define)
        if isinstance(node, ast.Expression):
            return self._visit(node.body)

        # If we encounter any other node type (Call, Name, Attribute, etc.),
        # we reject it immediately for security.
        raise ValueError(f"Forbidden syntax element: {type(node).__name__}")

class Calculator(core.module.Module):
    """Lets your AI do simple calculations without relying on it's own intelligence"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._calc = SafeCalculator()

    async def calc(self, expression: str):
        return self.result(self._calc.evaluate(expression))

    def _tests(self):
        test_cases = [
            "2 + 2",
            "4 * (5 - 2)",
            "2 ** 8",
            "10 / 3",
            "-5 + 10",
            "15 % 4",
            "2.5 * 2",
        ]

        print("Safe Calculator Tests")
        print("---------------------")

        for expr in test_cases:
            try:
                res = self._calc.evaluate(expr)
                print(f"{expr} = {res}")
            except Exception as e:
                print(f"{expr} -> Error: {e}")

        print("\nSecurity Tests (Injection Attempts)")
        print("-----------------------------------")

        dangerous_cases = [
            "__import__('os').system('echo PWNED')",
            "open('secret.txt', 'w')",
            "eval('2+2')",
            "globals()",
            " (lambda: 1)() "
        ]

        for expr in dangerous_cases:
            try:
                res = self._calc.evaluate(expr)
                print(f"SECURITY FAILURE: '{expr}' executed and returned {res}")
            except ValueError as e:
                print(f"Blocked: '{expr}' - Reason: {e}")
