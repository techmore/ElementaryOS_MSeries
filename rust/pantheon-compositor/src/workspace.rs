use std::collections::HashMap;

use smithay::{
    desktop::Window,
    utils::{Logical, Point},
};

#[derive(Default)]
pub(crate) struct WorkspaceManager {
    active: usize,
    workspaces: Vec<Vec<usize>>,
    windows: HashMap<usize, Window>,
    assignments: HashMap<usize, usize>,
    locations: HashMap<usize, Point<i32, Logical>>,
}

impl WorkspaceManager {
    pub fn new() -> Self {
        Self {
            active: 0,
            workspaces: vec![Vec::new()],
            ..Self::default()
        }
    }

    pub fn active(&self) -> usize {
        self.active
    }

    pub fn workspace_count(&self) -> usize {
        self.workspaces.len()
    }

    pub fn dynamic_workspace_index(&self) -> usize {
        self.workspaces.len()
    }

    pub fn add_window(&mut self, window: Window, location: Point<i32, Logical>) {
        let id = window.id();
        if let Some(previous) = self.assignments.remove(&id) {
            if let Some(windows) = self.workspaces.get_mut(previous) {
                windows.retain(|existing| *existing != id);
            }
        }
        self.windows.insert(id, window);
        self.assignments.insert(id, self.active);
        self.locations.insert(id, location);
        self.workspaces[self.active].push(id);
    }

    pub fn remove_window(&mut self, id: usize) {
        if let Some(workspace) = self.assignments.remove(&id)
            && let Some(windows) = self.workspaces.get_mut(workspace)
        {
            windows.retain(|existing| *existing != id);
        }
        self.windows.remove(&id);
        self.locations.remove(&id);
    }

    pub fn assign_window(&mut self, id: usize, workspace: usize) -> bool {
        if workspace >= self.workspaces.len() || !self.windows.contains_key(&id) {
            return false;
        }
        let Some(previous) = self.assignments.get(&id).copied() else {
            return false;
        };
        if previous == workspace {
            return true;
        }
        if let Some(windows) = self.workspaces.get_mut(previous) {
            windows.retain(|existing| *existing != id);
        }
        self.assignments.insert(id, workspace);
        self.workspaces[workspace].push(id);
        true
    }

    pub fn add_workspace(&mut self) -> usize {
        self.workspaces.push(Vec::new());
        self.workspaces.len() - 1
    }

    pub fn set_active(&mut self, workspace: usize) -> bool {
        if workspace >= self.workspaces.len() {
            return false;
        }
        self.active = workspace;
        true
    }

    pub fn reorder_workspace(&mut self, index: usize, new_index: usize) -> bool {
        if index >= self.workspaces.len() || new_index >= self.workspaces.len() {
            return false;
        }
        if index == new_index {
            return true;
        }
        let workspace = self.workspaces.remove(index);
        self.workspaces.insert(new_index, workspace);
        for (workspace_index, windows) in self.workspaces.iter().enumerate() {
            for id in windows {
                self.assignments.insert(*id, workspace_index);
            }
        }
        if self.active == index {
            self.active = new_index;
        } else if index < self.active && new_index >= self.active {
            self.active -= 1;
        } else if index > self.active && new_index <= self.active {
            self.active += 1;
        }
        true
    }

    pub fn workspace_for(&self, id: usize) -> Option<usize> {
        self.assignments.get(&id).copied()
    }

    pub fn window(&self, id: usize) -> Option<&Window> {
        self.windows.get(&id)
    }

    pub fn location(&self, id: usize) -> Option<Point<i32, Logical>> {
        self.locations.get(&id).copied()
    }

    pub fn set_location(&mut self, id: usize, location: Point<i32, Logical>) {
        if self.windows.contains_key(&id) {
            self.locations.insert(id, location);
        }
    }

    pub fn windows_in(&self, workspace: usize) -> Vec<(Window, Point<i32, Logical>)> {
        self.workspaces
            .get(workspace)
            .into_iter()
            .flatten()
            .filter_map(|id| Some((self.windows.get(id)?.clone(), self.location(*id)?)))
            .collect()
    }

    pub fn windows(&self) -> Vec<(Window, usize, Point<i32, Logical>)> {
        self.workspaces
            .iter()
            .enumerate()
            .flat_map(|(workspace, windows)| {
                windows.iter().filter_map(move |id| {
                    Some((
                        self.windows.get(id)?.clone(),
                        workspace,
                        self.location(*id)?,
                    ))
                })
            })
            .collect()
    }

    pub fn set_order_from_visible(&mut self, ordered_ids: &[usize], workspace: usize) {
        let Some(windows) = self.workspaces.get_mut(workspace) else {
            return;
        };
        let mut visible = ordered_ids
            .iter()
            .copied()
            .filter(|id| self.assignments.get(id) == Some(&workspace))
            .collect::<Vec<_>>();
        for id in windows.iter().copied() {
            if !visible.contains(&id) {
                visible.push(id);
            }
        }
        *windows = visible;
    }
}
