using UnityEngine;
using UnityEditor;

public static class DeleteExtraCameras
{
    [MenuItem("Tools/Delete All Cameras Except Main Camera")]
    public static void DeleteCameras()
    {
        Camera[] cameras = Object.FindObjectsByType<Camera>(
            FindObjectsInactive.Include,
            FindObjectsSortMode.None
        );

        int deleted = 0;

        foreach (Camera cam in cameras)
        {
            if (cam == null)
                continue;

            if (cam.gameObject.name == "Main Camera")
                continue;

            Undo.DestroyObjectImmediate(cam.gameObject);
            deleted++;
        }

        Debug.Log($"Deleted {deleted} extra camera(s). Main Camera kept.");
    }
}