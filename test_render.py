import json_repair

class ToolCallRenderer:
    def __init__(self):
        self.current_tool = None
        self.printed_values = {}

    def render(self, name: str, args_str: str):
        # If this is a new tool, print the header.
        if self.current_tool != name:
            print(f"\nCalling tool: {name}()")
            self.current_tool = name
            self.printed_values = {}

        try:
            data = json_repair.loads(args_str)
            if not isinstance(data, dict):
                return

            for key, value in data.items():
                val_str = str(value)
                previously_printed = self.printed_values.get(key, "")

                if val_str.startswith(previously_printed):
                    to_print = val_str[len(previously_printed):]
                else:
                    to_print = val_str

                if key not in self.printed_values:
                    print(f"\n{key}:", end="", flush=True)

                if to_print:
                    to_print = to_print.replace("\\\n", "\n")
                    print(to_print, end="", flush=True)

                self.printed_values[key] = val_str
        except Exception as e:
            print(f"Error: {e}")

renderer = ToolCallRenderer()

print("--- Test 1: Simple string appending ---")
renderer.render("test_tool", '{"param": "v"}')
renderer.render("test_tool", '{"param": "va"}')
renderer.render("test_tool", '{"param": "val"}')
renderer.render("test_tool", '{"param": "value"}')

print("\n\n--- Test 2: Multiple keys ---")
renderer.render("test_tool", '{"a": "1", "b": "2"}')
renderer.render("test_tool", '{"a": "1", "b": "2", "c": "3"}')
renderer.render("test_tool", '{"a": "1", "b": "23", "c": "3"}')

print("\n\n--- Test 3: Dictionary value ---")
renderer.render("test_tool", '{"params": {"a": 1}}')
renderer.render("test_tool", '{"params": {"a": 1, "b": 2}}')

print("\n\n--- Test 4: String with newline ---")
renderer.render("test_tool", '{"msg": "hello\\n"}')
renderer.render("test_tool", '{"msg": "hello\\nworld"}')

print("\n\n--- Test 5: Non-prefix change (the problem case?) ---")
renderer.render("test_tool", '{"a": "abc"}')
renderer.render("test_tool", '{"a": "axbc"}')
