import React, { useEffect, useState } from "react";
import { api } from "../../api/client.js";

const ALL_ROLES = ["EMPLOYEE", "IT_ENGINEER", "IT_MANAGER", "SYSTEM_ADMIN"];

export default function Users() {
  const [users, setUsers] = useState([]);
  const [editing, setEditing] = useState(null);
  const [newRoles, setNewRoles] = useState([]);
  const [error, setError] = useState(null);

  async function load() {
    try {
      setUsers(await api.get("/users"));
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, []);

  function startEdit(u) {
    setEditing(u.id);
    setNewRoles(u.roles || []);
  }
  function toggleRole(r) {
    setNewRoles(
      newRoles.includes(r) ? newRoles.filter((x) => x !== r) : [...newRoles, r],
    );
  }
  async function save() {
    try {
      await api.patch(`/users/${editing}/roles`, { roles: newRoles });
      setEditing(null);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (error)
    return (
      <div className="error">
        Cannot manage users: {error}
        <br />
        Only SYSTEM_ADMIN may access this page.
      </div>
    );
  return (
    <>
      <h2>Users & roles</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Department</th>
            <th>Roles</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.display_name}</td>
              <td>{u.email}</td>
              <td>{u.department || "—"}</td>
              <td>
                {editing === u.id ? (
                  <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {ALL_ROLES.map((r) => (
                      <label
                        key={r}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={newRoles.includes(r)}
                          onChange={() => toggleRole(r)}
                        />{" "}
                        {r}
                      </label>
                    ))}
                  </div>
                ) : (
                  (u.roles || []).join(", ")
                )}
              </td>
              <td>
                {editing === u.id ? (
                  <>
                    <button className="btn" onClick={save}>
                      Save
                    </button>{" "}
                    <button
                      className="btn secondary"
                      onClick={() => setEditing(null)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    className="btn secondary"
                    onClick={() => startEdit(u)}
                  >
                    Edit roles
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
