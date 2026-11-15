"""GUI/export indices. Config files carry an order tag for legacy migration."""
JPG = 0
PNG = 1
PDF = 2
ORDER = 'jpg,png,pdf'
LEGACY_TO_CURRENT = {0: PNG, 1: PDF, 2: JPG}
