using UnityEngine;
using UnityEditor;
using System.Linq;

public class CleanMuJoCoFly : EditorWindow
{
    [MenuItem("Tools/Clean Selected MuJoCo Fly")]
    public static void CleanSelected()
    {
        GameObject root = Selection.activeGameObject;

        if (root == null)
        {
            Debug.LogError("Najpierw zaznacz g³ówny obiekt muchy w Hierarchy.");
            return;
        }

        int removed = 0;

        var components = root.GetComponentsInChildren<Component>(true);

        foreach (var component in components.ToList())
        {
            if (component == null)
                continue;

            var type = component.GetType();

            if (type.Namespace != null &&
                type.Namespace.StartsWith("Mujoco"))
            {
                Undo.DestroyObjectImmediate(component);
                removed++;
            }
        }

        Debug.Log($"Gotowe. Usuniêto {removed} komponentów MuJoCo z {root.name}.");
    }
}