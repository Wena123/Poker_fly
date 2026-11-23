using UnityEngine;
using UnityEditor;

public static class FixPokerAnchors
{
    [MenuItem("Tools/Fix Poker Anchors")]
    public static void FixAnchors()
    {
        string[] rootNames =
        {
            "BetAnchors",
            "ChipAnchors",
            "PotArchorn"
        };

        int fixedCount = 0;

        foreach (string rootName in rootNames)
        {
            GameObject root = GameObject.Find(rootName);

            if (root == null)
            {
                Debug.LogWarning("Nie znaleziono: " + rootName);
                continue;
            }

            FixTransform(root.transform);
            fixedCount++;

            foreach (Transform child in root.GetComponentsInChildren<Transform>(true))
            {
                if (child == root.transform)
                    continue;

                FixTransform(child);
                fixedCount++;
            }
        }

        Debug.Log("Gotowe. Poprawiono " + fixedCount + " obiektów.");
    }

    private static void FixTransform(Transform t)
    {
        Undo.RecordObject(t, "Fix Poker Anchors");

        t.localRotation = Quaternion.identity;
        t.localScale = Vector3.one;

        EditorUtility.SetDirty(t);
    }
}