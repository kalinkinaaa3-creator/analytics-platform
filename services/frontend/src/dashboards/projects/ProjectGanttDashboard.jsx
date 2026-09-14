import { useEffect, useMemo, useRef, useState } from "react";
import { DateRangePicker } from "../../components/DateRangePicker";
import { useDropdownPosition } from "../../components/useDropdownPosition";
import "./list_project.css";

const FILTERS = [
  ["folder_lvl1", "Группы", "folder_lvl1"],
  ["folder_lvl2", "Группа (уровень 2)", "folder_lvl2"],
  ["folder_lvl3", "Группа (уровень 3)", "folder_lvl3"],
  ["project_name", "Наименование", "name"],
  ["project_type", "Тип", "type"],
  ["department", "Подразделение", "department"],
  ["project_manager", "Ответственный", "managers"],
  ["project_status", "Статус", "statuses"],
  ["deviation_project", "Выполнение", "deviation"],
];

function normalizeSelected(value) {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  return value ? [String(value)] : [];
}

function ProjectMultiSelect({ label, options, selected, onChange }) {
  const rootRef = useRef(null);
  const menuRef = useRef(null);
  const selectedRef = useRef(selected);
  const draftRef = useRef(selected);
  const onChangeRef = useRef(onChange);
  const openRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(selected);
  const [search, setSearch] = useState("");

  useEffect(() => {
    selectedRef.current = selected;
    onChangeRef.current = onChange;
    if (!open) {
      draftRef.current = selected;
    }
  }, [selected, onChange, open]);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("ru-RU");
    return options.filter((value) => !needle || String(value).toLocaleLowerCase("ru-RU").includes(needle));
  }, [options, search]);

  function updateDraft(next) {
    draftRef.current = next;
    setDraft(next);
  }

  function commit() {
    const current = selectedRef.current;
    const next = draftRef.current;
    if (current.length !== next.length || current.some((value, index) => value !== next[index])) {
      onChangeRef.current(next);
    }
  }

  function closeMenu() {
    commit();
    openRef.current = false;
    setOpen(false);
    setSearch("");
  }

  useEffect(() => {
    function closeOutside(event) {
      if (openRef.current && !rootRef.current?.contains(event.target)) {
        const current = selectedRef.current;
        const next = draftRef.current;
        if (current.length !== next.length || current.some((value, index) => value !== next[index])) {
          onChangeRef.current(next);
        }
        openRef.current = false;
        setOpen(false);
        setSearch("");
      }
    }
    document.addEventListener("mousedown", closeOutside);
    return () => document.removeEventListener("mousedown", closeOutside);
  }, []);

  const { menuStyle, resetPosition } = useDropdownPosition({
    open,
    rootRef,
    menuRef,
    contentKey: `${visible.length}:${search}`,
  });

  function toggleMenu() {
    if (open) {
      closeMenu();
      return;
    }
    updateDraft(selected);
    resetPosition();
    openRef.current = true;
    setOpen(true);
  }

  function toggleValue(value) {
    updateDraft(draft.includes(value) ? draft.filter((item) => item !== value) : [...draft, value]);
  }

  function selectVisible() {
    updateDraft([...new Set([...draft, ...visible])]);
  }

  const shownSelection = open ? draft : selected;

  return (
    <div className={`project-filter${open ? " project-filter--open" : ""}`} ref={rootRef}>
      <label>{label}</label>
      <button
        type="button"
        className="project-multiselect__control"
        aria-expanded={open}
        onClick={toggleMenu}
      >
        <span>{shownSelection.length ? `Выбрано: ${shownSelection.length}` : "Все"}</span>
        <i aria-hidden="true">▾</i>
      </button>
      {open && (
        <div ref={menuRef} className="project-multiselect__menu" style={menuStyle}>
          <input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Поиск…" />
          <div className="project-multiselect__actions">
            <button type="button" disabled={!visible.length} onClick={selectVisible}>Выбрать найденные</button>
            <button type="button" disabled={!draft.length && !search} onClick={() => { updateDraft([]); setSearch(""); }}>Очистить</button>
          </div>
          <div className="project-multiselect__options">
            {visible.map((value) => (
              <label key={value}>
                <input type="checkbox" checked={draft.includes(value)} onChange={() => toggleValue(value)} />
                <span>{value}</span>
              </label>
            ))}
            {!visible.length && <p>Нет значений</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function formatDate(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function firstCellStyle(isNode = false) {
  return {
    fontWeight: isNode ? "bold" : undefined,
    top: "auto",
  };
}

function IndentedName({ indentPx, children }) {
  return (
    <span
      style={{
        display: "block",
        paddingLeft: `${indentPx}px`,
        maxWidth: "100%",
        overflow: "hidden",
        whiteSpace: "nowrap",
        textOverflow: "ellipsis",
        boxSizing: "border-box",
      }}
    >
      {children}
    </span>
  );
}

function GanttBar({ bar, type, title }) {
  if (!bar) return null;

  return (
    <div
      className={type === "fact" ? "gantt-bar-fact tooltip" : "gantt-bar tooltip"}
      title={title || ""}
      style={{
        position: "absolute",
        top: 0,
        left: `${bar.offset}px`,
        width: `${bar.width}px`,
        height: "32px",
      }}
    />
  );
}

function TodayLine({ offset }) {
  if (offset === null || offset === undefined || offset === "") return null;

  return <div className="today-line" style={{ left: `${offset}px` }} />;
}

function BarCell({ months, bar, type, title, todayOffset }) {
  return (
    <td colSpan={months.length} style={{ position: "relative", height: "32px" }}>
      <GanttBar bar={bar} type={type} title={title} />
      <TodayLine offset={todayOffset} />
    </td>
  );
}

function PlanFactRows({
  id,
  rowClassName,
  factClassName,
  name,
  manager,
  status,
  planStart,
  planEnd,
  factStart,
  factEnd,
  barPlan,
  barFact,
  tooltipPlan,
  tooltipFact,
  months,
  todayOffset,
  isNode = false,
  hasToggle = false,
  indentPx = 0,
  expanded = false,
  visible = true,
  onToggle,
}) {
  return (
    <>
      <tr
        className={rowClassName}
        data-id={id}
        style={{ display: visible ? "" : "none" }}
      >
        <td className="col-name" style={firstCellStyle(isNode)} title={name}>
          <IndentedName indentPx={indentPx}>
            {hasToggle && (
              <span
                className="toggle-node"
                onClick={() => onToggle(id)}
                style={{ cursor: "pointer" }}
              >
                {expanded ? "[-]" : "[+]"}
              </span>
            )}{" "}
            {name}
          </IndentedName>
        </td>

        <td>{manager || ""}</td>
        <td>{status || ""}</td>
        <td className="type-plan">План</td>
        <td>{formatDate(planStart)}</td>
        <td>{formatDate(planEnd)}</td>

        <BarCell
          months={months}
          bar={barPlan}
          type="plan"
          title={tooltipPlan}
          todayOffset={todayOffset}
        />
      </tr>

      <tr className={factClassName} style={{ display: visible ? "" : "none" }}>
        <td style={firstCellStyle(isNode)}>
          <IndentedName indentPx={indentPx}></IndentedName>
        </td>
        <td></td>
        <td></td>
        <td className="type-fact">Факт</td>
        <td>{formatDate(factStart)}</td>
        <td>{formatDate(factEnd)}</td>

        <BarCell
          months={months}
          bar={barFact}
          type="fact"
          title={tooltipFact}
          todayOffset={todayOffset}
        />
      </tr>
    </>
  );
}

function ProjectSubtaskRows({
  subtask,
  className,
  months,
  todayOffset,
  indentPx,
  visible,
}) {
  return (
    <>
      <tr
        className={className}
        title={subtask.subtask_name}
        style={{ display: visible ? "" : "none" }}
      >
        <td style={firstCellStyle(false)}>
          <IndentedName indentPx={indentPx}>
            {subtask.subtask_name}
          </IndentedName>
        </td>

        <td>{subtask.subtask_responsible}</td>
        <td>{subtask.subtask_status}</td>
        <td className="type-plan">План</td>
        <td>{formatDate(subtask.sign?.plan?.start)}</td>
        <td>{formatDate(subtask.sign?.plan?.end)}</td>

        <BarCell
          months={months}
          bar={subtask.bar_plan}
          type="plan"
          title={subtask.tooltip_plan}
          todayOffset={todayOffset}
        />
      </tr>

      <tr className={className} style={{ display: visible ? "" : "none" }}>
        <td style={firstCellStyle(false)}>
          <IndentedName indentPx={indentPx}></IndentedName>
        </td>
        <td></td>
        <td></td>
        <td className="type-fact">Факт</td>
        <td>{formatDate(subtask.sign_display?.fact?.start)}</td>
        <td>{formatDate(subtask.sign_display?.fact?.end)}</td>

        <BarCell
          months={months}
          bar={subtask.bar_fact}
          type="fact"
          title={subtask.tooltip_fact}
          todayOffset={todayOffset}
        />
      </tr>
    </>
  );
}

function FragmentWrapper({ children }) {
  return <>{children}</>;
}

function HierarchyRows({
  nodes,
  rootId,
  parentId,
  months,
  todayOffset,
  level,
  expandedIds,
  onToggle,
  parentVisible,
}) {
  return (
    <>
      {nodes.map((node) => {
        const expanded = expandedIds.has(node.id);
        const visible = parentVisible;
        const childrenVisible = visible && expanded;

        const nodeIndent = (level + 1) * 20;
        const subtaskIndent = (level + 2) * 20;

        return (
          <FragmentWrapper key={node.id}>
            <PlanFactRows
              id={node.id}
              rowClassName={`node-row child-of-${parentId} child-of-${rootId}`}
              factClassName={`fact-row-${node.id} child-of-${parentId} child-of-${rootId}`}
              name={node.name}
              manager={node.knot_responsible}
              status={node.knot_status}
              planStart={node.sign?.plan?.start}
              planEnd={node.sign?.plan?.end}
              factStart={node.sign_display?.fact?.start}
              factEnd={node.sign_display?.fact?.end}
              barPlan={node.bar_plan}
              barFact={node.bar_fact}
              tooltipPlan={node.tooltip_plan}
              tooltipFact={node.tooltip_fact}
              months={months}
              todayOffset={todayOffset}
              isNode
              hasToggle
              indentPx={nodeIndent}
              expanded={expanded}
              visible={visible}
              onToggle={onToggle}
            />

            {node.subtasks?.map((subtask, index) => (
              <ProjectSubtaskRows
                key={`${node.id}-sub-${index}`}
                subtask={subtask}
                className={`child-of-${node.id} child-of-${rootId}`}
                months={months}
                todayOffset={todayOffset}
                indentPx={subtaskIndent}
                visible={childrenVisible}
              />
            ))}

            {Boolean(node.children?.length) && (
              <HierarchyRows
                nodes={node.children}
                rootId={rootId}
                parentId={node.id}
                months={months}
                todayOffset={todayOffset}
                level={level + 1}
                expandedIds={expandedIds}
                onToggle={onToggle}
                parentVisible={childrenVisible}
              />
            )}
          </FragmentWrapper>
        );
      })}
    </>
  );
}

function collectHierarchyIds(nodes, result = []) {
  nodes.forEach((node) => {
    result.push(node.id);

    if (node.children?.length) {
      collectHierarchyIds(node.children, result);
    }
  });

  return result;
}

export function ProjectGanttDashboard({ data, onFiltersChange }) {
  const projects = useMemo(() => data?.projects_tree || [], [data?.projects_tree]);
  const months = data?.months_list || [];
  const filters = useMemo(() => data?.filters || {}, [data?.filters]);
  const filterValues = data?.filter_values || {};
  const todayOffset = data?.today_offset;

  const [localFilters, setLocalFilters] = useState(filters);
  const [expandedIds, setExpandedIds] = useState(new Set());

  const idsByNode = useMemo(() => {
    const map = new Map();

    projects.forEach((project) => {
      const ids = [project.id];

      if (project.hierarchy?.length) {
        collectHierarchyIds(project.hierarchy, ids);
      }

      map.set(project.id, ids);

      function mapHierarchy(nodes) {
        nodes.forEach((node) => {
          const nodeIds = [node.id];

          if (node.children?.length) {
            collectHierarchyIds(node.children, nodeIds);
            mapHierarchy(node.children);
          }

          map.set(node.id, nodeIds);
        });
      }

      if (project.hierarchy?.length) {
        mapHierarchy(project.hierarchy);
      }
    });

    return map;
  }, [projects]);

  const allNodeIds = useMemo(() => {
    return Array.from(
      new Set(
        projects.flatMap((project) => idsByNode.get(project.id) || [project.id])
      )
    );
  }, [projects, idsByNode]);

  function applyFilters(next) {
    setLocalFilters(next);

    if (onFiltersChange) {
      onFiltersChange(next);
    }
  }

  function handleFilterChange(name, value) {
    applyFilters({
      ...localFilters,
      [name]: value,
    });
  }

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    setLocalFilters(filters);
    setExpandedIds(new Set());
  }, [filters, projects]);
  /* eslint-enable react-hooks/set-state-in-effect */

  function resetFilters() {
    const year = new Date().getFullYear() - 1;
    const nextYear = year + 2;

    const next = {
      project_name: [],
      project_type: [],
      department: [],
      deviation_project: [],
      project_manager: [],
      project_status: [],
      folder_lvl1: [],
      folder_lvl2: [],
      folder_lvl3: [],
      project_start: `${year}-01-01`,
      project_end: `${nextYear}-12-31`,
    };

    setLocalFilters(next);
    setExpandedIds(new Set());

    if (onFiltersChange) {
      onFiltersChange(next);
    }
  }

  function toggleNode(id) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      const idsToToggle = idsByNode.get(id) || [id];
      const isExpanded = next.has(id);

      if (isExpanded) {
        idsToToggle.forEach((itemId) => next.delete(itemId));
      } else {
        idsToToggle.forEach((itemId) => next.add(itemId));
      }

      return next;
    });
  }

  function toggleAll() {
    setExpandedIds((prev) => {
      if (prev.size) {
        return new Set();
      }

      return new Set(allNodeIds);
    });
  }

  const allExpanded = expandedIds.size > 0;
  const resetYear = new Date().getFullYear() - 1;
  const projectResetRange = {
    start: `${resetYear}-01-01`,
    end: `${resetYear + 2}-12-31`,
  };

  return (
    <div className="project-gantt-dashboard" data-last-updated={data?.last_update || ""}>
      <h2>Проекты</h2>

      <form id="filterForm" onSubmit={(event) => event.preventDefault()}>
        <div className="project-filter-actions">
          <button
            type="button"
            id="resetFilters"
            className="filters-reset"
            onClick={resetFilters}
          >
            Очистить
          </button>
        </div>

        <div className="project-filter-grid">
          {FILTERS.map(([name, label, valuesKey]) => (
            <ProjectMultiSelect
              key={name}
              label={label}
              options={filterValues[valuesKey] || []}
              selected={normalizeSelected(localFilters[name])}
              onChange={(value) => handleFilterChange(name, value)}
            />
          ))}

          <DateRangePicker
            key={`${localFilters.project_start}:${localFilters.project_end}`}
            start={localFilters.project_start || projectResetRange.start}
            end={localFilters.project_end || projectResetRange.end}
            resetRange={projectResetRange}
            onChange={({ start, end }) => applyFilters({
              ...localFilters,
              project_start: start,
              project_end: end,
            })}
          />
        </div>
      </form>

      <div className="gantt-table-wrapper">
        <table id="head" className="visible">
          <thead>
            <tr>
              <th>
                <span id="toggle-all" style={{ cursor: "pointer" }} onClick={toggleAll}>
                  {allExpanded ? "[-]" : "[+]"}
                </span>{" "}
                Наименование
              </th>
              <th>Ответственный</th>
              <th>Статус</th>
              <th>Тип</th>
              <th>Начало</th>
              <th>Окончание</th>

              {months.map((month, index) => (
                <th
                  key={`${month.label}-${index}`}
                  className="month-col"
                  style={{ width: "62px", boxSizing: "border-box" }}
                >
                  {month.label}
                </th>
              ))}
            </tr>
          </thead>

          <tbody id="projectsTableBody">
            {projects.map((project) => {
              const expanded = expandedIds.has(project.id);

              return (
                <FragmentWrapper key={project.id}>
                  <PlanFactRows
                    id={project.id}
                    rowClassName="node-row"
                    factClassName={`fact-row-${project.id}`}
                    name={project.project_name}
                    manager={project.project_manager}
                    status={project.project_status}
                    planStart={project.sign?.plan?.start}
                    planEnd={project.sign?.plan?.end}
                    factStart={project.sign_display?.fact?.start}
                    factEnd={project.sign_display?.fact?.end}
                    barPlan={project.bar_plan}
                    barFact={project.bar_fact}
                    tooltipPlan={project.tooltip_plan}
                    tooltipFact={project.tooltip_fact}
                    months={months}
                    todayOffset={todayOffset}
                    isNode
                    hasToggle
                    indentPx={0}
                    expanded={expanded}
                    visible
                    onToggle={toggleNode}
                  />

                  {project.subtasks?.map((subtask, index) => (
                    <ProjectSubtaskRows
                      key={`${project.id}-sub-${index}`}
                      subtask={subtask}
                      className={`child-of-${project.id}`}
                      months={months}
                      todayOffset={todayOffset}
                      indentPx={20}
                      visible={expanded}
                    />
                  ))}

                  {Boolean(project.hierarchy?.length) && (
                    <HierarchyRows
                      nodes={project.hierarchy}
                      rootId={project.id}
                      parentId={project.id}
                      months={months}
                      todayOffset={todayOffset}
                      level={1}
                      expandedIds={expandedIds}
                      onToggle={toggleNode}
                      parentVisible={expanded}
                    />
                  )}
                </FragmentWrapper>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
