from core.plugin_loader import write_skill_template
from pathlib import Path
write_skill_template(Path('skills'))
print('Template created')