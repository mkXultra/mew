Add a locker delivery channel to the label rules.

This phase uses the current layout:
`src/golden_convention/current_layout/label_rules.py`.

`delivery_label("locker", code)` should return
`LOCKER-CODE: hold for pickup`, uppercasing and trimming the code the same way
the existing channels do.

Do not create or use legacy layout paths.
